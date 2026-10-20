"""
36개 모의면접 영상에서 평가모델 학습용 '객관적' feature를 추출한다.

채점표의 7개 세부점수는 사람이 매긴 주관 점수이고 최종점수가 그 가중합이므로
feature로 쓸 수 없다. 여기서는 영상/음성에서 계산되는 지표만 뽑는다.

  음성  : verbal_module/api.analyze_file  (Whisper STT + filler/stutter/pause/속도/음량)
  시선  : nonverbal_module/eye_tracker.py (mediapipe blendshape)
  표정  : hsemotion (시선 루프에서 잘라낸 얼굴 crop 재사용)
  자세  : nonverbal_module/posture_rtmpose_3d.py 의 PostureAnalyzer3D (RTMW3D, GPU)

실행:
  LD_LIBRARY_PATH=/opt/conda/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/conda/lib \
      python3 extract_features.py [--sample-fps 2] [--only 영상ID]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("RTMPOSE_CUDA_READY", "1")  # posture 모듈의 os.execv 재실행 방지

import cv2
import numpy as np

CSM_DIR = Path("/workspace/CSM")
VIDEO_DIR = CSM_DIR / "eval_model" / "data" / "raw_videos"
OUT_DIR = CSM_DIR / "eval_model" / "data" / "features"
AUDIO_TMP_DIR = CSM_DIR / "eval_model" / "data" / "_audio_tmp"

sys.path.append(str(CSM_DIR / "verbal_module"))
sys.path.append(str(CSM_DIR / "backend"))
sys.path.append(str(CSM_DIR / "nonverbal_module"))

EMOTION_NEGATIVE = {"Anger", "Disgust", "Fear", "Sadness", "Contempt"}


# ── 음성/언어 ────────────────────────────────────────────────────────────────

def _patch_whisper_to_gpu():
    """기존 transcriber.load_model 은 device='cpu'/int8 고정이라 36개 배치가 너무 느리다.
    원본 파일은 건드리지 않고 로더만 GPU(float16)로 교체한다."""
    import analyzers
    import analyzers.transcriber as transcriber

    def gpu_load_model(model_size: str = "medium"):
        from faster_whisper import WhisperModel
        return WhisperModel(model_size, device="cuda", compute_type="float16")

    analyzers.load_model = gpu_load_model
    transcriber.load_model = gpu_load_model


def extract_language_features(video_path: Path, audio_path: Path) -> dict:
    _patch_whisper_to_gpu()
    import api as lang_api

    # moviepy 2.x 에서 moviepy.editor 가 제거되어 preprocessor.extract_audio 대신 ffmpeg 직접 호출
    if not audio_path.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
             "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
            check=True,
        )

    report = lang_api.analyze_file(str(audio_path))
    if report.get("status") != "success":
        raise RuntimeError(f"language analysis failed: {report.get('error_message')}")

    metrics = report.get("metrics", {})
    raw = report.get("raw_data", {})

    total = float(raw.get("total_duration_sec") or 0.0)
    pure = float(raw.get("pure_speech_time_sec") or 0.0)
    minutes = max(total / 60.0, 1e-6)

    pauses = metrics.get("long_pauses", {}).get("occurrences", []) or []
    pause_durs = [float(p.get("duration") or 0.0) for p in pauses]
    volume = metrics.get("volume_stability", {})

    return {
        "spm": float(metrics.get("speech_rate", {}).get("spm") or 0.0),
        "filler_count": int(metrics.get("filler_word", {}).get("count") or 0),
        "filler_per_min": (metrics.get("filler_word", {}).get("count") or 0) / minutes,
        "stutter_count": int(metrics.get("stuttering", {}).get("count") or 0),
        "stutter_per_min": (metrics.get("stuttering", {}).get("count") or 0) / minutes,
        "long_pause_count": len(pauses),
        "long_pause_per_min": len(pauses) / minutes,
        "long_pause_total_sec": float(sum(pause_durs)),
        "long_pause_max_sec": float(max(pause_durs)) if pause_durs else 0.0,
        "long_pause_ratio": float(sum(pause_durs)) / max(total, 1e-6),
        "volume_rms_mean": float(volume.get("rms_mean") or 0.0),
        "volume_rms_std": float(volume.get("rms_std") or 0.0),
        "volume_cv": float(volume.get("cv") or 0.0),
        "total_duration_sec": total,
        "pure_speech_time_sec": pure,
        "speech_ratio": pure / max(total, 1e-6),
        "word_count": len((raw.get("transcript") or "").split()),
    }


# ── 시선 + 표정 (프레임 1회 순회) ────────────────────────────────────────────
# nonverbal_module/vision_features.py 로 이동 — backend 라이브 분석과 완전히 같은
# 코드로 feature를 뽑아야 학습된 모델이 실서비스 입력에서도 의미가 있다.

def extract_gaze_emotion_features(video_path: Path, sample_fps: float) -> dict:
    from vision_features import extract_gaze_emotion
    record = extract_gaze_emotion(str(video_path), sample_fps=sample_fps, device="cuda")
    record.pop("_gaze_summary", None)
    record.pop("_emotion_counts", None)
    record.pop("_expression_deductions", None)
    return record


# ── 자세 ─────────────────────────────────────────────────────────────────────

def _load_posture_module():
    path = CSM_DIR / "nonverbal_module" / "posture_rtmpose_3d.py"
    spec = importlib.util.spec_from_file_location("posture_rtmpose_3d", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_posture_features(video_path: Path, sample_fps: float, posture_mod=None) -> dict:
    from vision_features import extract_posture
    record = extract_posture(str(video_path), sample_fps=sample_fps, device="cuda")
    record.pop("_posture_deductions", None)
    return record


# ── 드라이버 ─────────────────────────────────────────────────────────────────

def video_list() -> list[tuple[str, str, Path]]:
    items = []
    for cls_dir in sorted(VIDEO_DIR.iterdir()):
        if cls_dir.is_dir():
            for video in sorted(cls_dir.glob("*.mp4")):
                items.append((video.stem, cls_dir.name, video))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--only", default=None, help="특정 video_id만 처리")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_TMP_DIR.mkdir(parents=True, exist_ok=True)
    posture_mod = _load_posture_module()

    videos = video_list()
    if args.only:
        videos = [v for v in videos if v[0] == args.only]

    print(f"처리 대상: {len(videos)}개 영상 (sample_fps={args.sample_fps})\n", flush=True)

    for i, (video_id, cls, path) in enumerate(videos, 1):
        out_path = OUT_DIR / f"{video_id}.json"
        if args.skip_existing and out_path.exists():
            print(f"[{i}/{len(videos)}] {video_id} — 이미 완료, 건너뜀", flush=True)
            continue

        print(f"[{i}/{len(videos)}] {video_id} 처리 시작...", flush=True)
        record = {"video_id": video_id, "class_dir": cls, "video_path": str(path), "errors": {}}
        t_start = time.time()

        for name, fn in (
            ("language", lambda: extract_language_features(path, AUDIO_TMP_DIR / f"{video_id}.wav")),
            ("gaze_emotion", lambda: extract_gaze_emotion_features(path, args.sample_fps)),
            ("posture", lambda: extract_posture_features(path, args.sample_fps, posture_mod)),
        ):
            t0 = time.time()
            try:
                record.update(fn())
                print(f"    {name} 완료 ({time.time() - t0:.1f}s)", flush=True)
            except Exception as e:
                record["errors"][name] = f"{type(e).__name__}: {e}"
                print(f"    {name} 실패: {e}", flush=True)
                traceback.print_exc()

        record["elapsed_sec"] = round(time.time() - t_start, 1)
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    → 저장 완료 ({record['elapsed_sec']}s)\n", flush=True)

    print("전체 완료")


if __name__ == "__main__":
    main()
