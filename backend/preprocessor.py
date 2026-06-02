"""
preprocessor.py
---------------
비디오 전처리 파이프라인:
  - 오디오 추출         (언어모듈용 16kHz WAV)
  - 프레임 추출         (비언어모듈용 JPEG, 1fps)
  - 화자 분리 기반 답변 구간 분리
  - 오디오 클립 반환    (감점 구간 프론트엔드 재생용)
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

_LANG_DIR = Path(__file__).parent.parent / "verbal_module"
if str(_LANG_DIR) not in sys.path:
    sys.path.append(str(_LANG_DIR))   # insert(0) 금지 — 언어모듈/main.py 충돌 방지

# 답변 경계 파라미터 (면접자 발화 사이 이 간격 이상이면 새 답변)
_ANSWER_GAP_SEC  = 3.0
_MIN_ANSWER_SEC  = 3.0


# ── 오디오 추출 ──────────────────────────────────────────────────────────────

def extract_audio(video_path: str, output_path: str) -> str:
    """비디오에서 오디오를 16kHz WAV로 추출합니다."""
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(video_path)
    try:
        if clip.audio is None:
            raise ValueError("오디오 트랙이 없는 영상입니다")
        clip.audio.write_audiofile(output_path, fps=16000, logger=None)
    finally:
        clip.close()
    return output_path


# ── 프레임 추출 ──────────────────────────────────────────────────────────────

def extract_frames(video_path: str, output_dir: str, fps: float = 1.0) -> list[dict]:
    """
    비디오에서 프레임을 추출하여 JPEG 파일로 저장합니다.
    비언어모듈(자세·표정·시선)의 입력으로 사용됩니다.

    Returns
    -------
    list of {"timestamp": float, "path": str}
    """
    import numpy as np
    from moviepy.editor import VideoFileClip
    from PIL import Image

    os.makedirs(output_dir, exist_ok=True)
    frames_info: list[dict] = []

    clip = VideoFileClip(video_path)
    try:
        for t in np.arange(0, clip.duration, 1.0 / fps):
            t = float(t)
            frame    = clip.get_frame(t)           # RGB numpy array (H, W, 3)
            filename = f"frame_{t:08.3f}.jpg"
            path     = os.path.join(output_dir, filename)
            Image.fromarray(frame).save(path, quality=85)
            frames_info.append({"timestamp": round(t, 3), "path": path})
    finally:
        clip.close()

    return frames_info


def save_frames_metadata(frames_info: list[dict], output_path: str) -> None:
    """비언어모듈이 참조할 frames_metadata.json을 저장합니다."""
    meta = [
        {"timestamp": f["timestamp"], "filename": Path(f["path"]).name}
        for f in frames_info
    ]
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)


# ── 화자 분리 기반 답변 구간 분리 ────────────────────────────────────────────

def get_answer_segments(
    audio_path: str,
    hf_token: str = "",
) -> tuple[int, list[dict]]:
    """
    화자 분리를 통해 답변 구간을 분리합니다.

    로직:
      - HF_TOKEN 있고 화자 2명 이상: pyannote로 면접자 구간 추출 →
        _ANSWER_GAP_SEC 기준으로 그룹핑하여 답변 단위 반환
      - HF_TOKEN 없거나 화자 1명: 전체를 하나의 구간으로 반환

    Returns
    -------
    (speaker_count, answer_segments)
      speaker_count   : 감지된 화자 수 (0 = 분리 실패)
      answer_segments : [{"index": int, "start": float, "end": float | None}]
                        end=None 이면 파일 끝까지
    """
    if not hf_token:
        return 1, [{"index": 0, "start": 0.0, "end": None}]

    try:
        from analyzers.diarization import load_pipeline, analyze_speakers

        pipeline      = load_pipeline(hf_token)
        info          = analyze_speakers(audio_path, pipeline)
        speaker_count = info["speaker_count"]

        if speaker_count >= 2:
            segs = _group_into_answers(info["interviewee_segments"])
        else:
            segs = [{"index": 0, "start": 0.0, "end": None}]

        return speaker_count, segs

    except Exception as e:
        print(f"[Diarization] 실패, 전체 오디오로 분석합니다: {e}")
        return 0, [{"index": 0, "start": 0.0, "end": None}]


def _group_into_answers(
    interviewee_segs: list[dict],
    gap_threshold: float = _ANSWER_GAP_SEC,
    min_duration:  float = _MIN_ANSWER_SEC,
) -> list[dict]:
    """면접자 발화 구간들을 답변 단위로 묶습니다."""
    if not interviewee_segs:
        return [{"index": 0, "start": 0.0, "end": None}]

    merged = [{"start": interviewee_segs[0]["start"], "end": interviewee_segs[0]["end"]}]
    for seg in interviewee_segs[1:]:
        gap = seg["start"] - merged[-1]["end"]
        if gap < gap_threshold:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append({"start": seg["start"], "end": seg["end"]})

    result = []
    for m in merged:
        if (m["end"] - m["start"]) >= min_duration:
            result.append({"index": len(result), "start": m["start"], "end": m["end"]})

    return result or [{"index": 0, "start": 0.0, "end": None}]


# ── 오디오 구간 추출 ─────────────────────────────────────────────────────────

def extract_audio_segment(
    audio_path: str,
    start: float,
    end: float,
    output_path: str,
) -> str:
    """오디오의 특정 구간을 WAV 파일로 저장합니다."""
    import librosa
    import soundfile as sf

    y, sr = librosa.load(audio_path, sr=None, mono=True,
                         offset=start, duration=end - start)
    sf.write(output_path, y, sr)
    return output_path


def get_audio_clip_bytes(
    audio_path: str,
    start: float,
    end: float,
    context: float = 0.5,
) -> bytes:
    """
    감점 구간 전후 context초 포함한 오디오를 WAV bytes로 반환합니다.
    프론트엔드 <audio> 태그에서 직접 재생됩니다.
    """
    import librosa
    import soundfile as sf

    info       = sf.info(audio_path)
    clip_start = max(0.0, start - context)
    clip_end   = min(info.duration, end + context)

    y, sr = librosa.load(audio_path, sr=None, mono=True,
                         offset=clip_start, duration=clip_end - clip_start)

    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()
