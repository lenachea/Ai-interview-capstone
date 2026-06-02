"""
analyzers/diarization.py
------------------------
pyannote.audio 기반 화자 분리 모듈.
면접자(발화 시간이 가장 긴 화자)의 구간만 추출합니다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

import numpy as np


def _load_audio_tensor(audio_path: str):
    """soundfile로 오디오를 읽어 pyannote 입력 딕셔너리로 반환합니다.
    torchcodec(Windows FFmpeg DLL 미설치 환경)을 우회합니다."""
    import torch
    import soundfile as sf

    data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
    # soundfile → (frames, channels), pyannote → (channels, frames)
    waveform = torch.tensor(data.T)
    return {"waveform": waveform, "sample_rate": sr}


def load_pipeline(hf_token: str):
    from pyannote.audio import Pipeline
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,   # use_auth_token → token
    )
    return pipeline


def get_interviewee_segments(
    audio_path: str,
    pipeline,
    min_segment_duration: float = 0.3,
) -> list[dict]:
    """
    화자 분리 후 면접자(발화 시간이 가장 긴 화자) 구간을 반환합니다.

    Parameters
    ----------
    audio_path : str
        분석할 음성 파일 경로
    pipeline : pyannote Pipeline
        load_pipeline()으로 로드한 파이프라인
    min_segment_duration : float
        이 길이(초) 미만의 구간은 노이즈로 간주하여 제외

    Returns
    -------
    list[dict]
        [{"start": float, "end": float}, ...]
        면접자 발화 구간 목록
    """
    diarization = pipeline(_load_audio_tensor(audio_path)).speaker_diarization

    # 화자별 총 발화 시간 및 구간 수집
    speaker_duration: dict[str, float] = defaultdict(float)
    speaker_segments: dict[str, list[dict]] = defaultdict(list)

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        duration = turn.end - turn.start
        if duration < min_segment_duration:
            continue
        speaker_duration[speaker] += duration
        speaker_segments[speaker].append({
            "start": round(turn.start, 3),
            "end":   round(turn.end,   3),
        })

    if not speaker_duration:
        return []

    # 발화 시간이 가장 긴 화자 = 면접자
    interviewee = max(speaker_duration, key=lambda s: speaker_duration[s])

    total = sum(speaker_duration.values())
    print(f"[Diarization] 감지된 화자 수: {len(speaker_duration)}")
    for spk, dur in sorted(speaker_duration.items(), key=lambda x: -x[1]):
        flag = " ← 면접자" if spk == interviewee else ""
        print(f"  {spk}: {dur:.1f}초 ({dur/total*100:.0f}%){flag}")

    return sorted(speaker_segments[interviewee], key=lambda x: x["start"])


def analyze_speakers(
    audio_path: str,
    pipeline,
    min_segment_duration: float = 0.3,
) -> dict:
    """
    화자 분리를 1회 실행하여 화자 수와 면접자 구간을 함께 반환합니다.

    Returns
    -------
    dict:
      speaker_count        : int   — 감지된 화자 수
      interviewee_segments : list  — 화자 2명 이상일 때 면접자 구간, 1명이면 []
    """
    diarization = pipeline(_load_audio_tensor(audio_path)).speaker_diarization

    speaker_duration: dict[str, float] = defaultdict(float)
    speaker_segments: dict[str, list[dict]] = defaultdict(list)

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        dur = turn.end - turn.start
        if dur < min_segment_duration:
            continue
        speaker_duration[speaker] += dur
        speaker_segments[speaker].append({
            "start": round(turn.start, 3),
            "end":   round(turn.end,   3),
        })

    speaker_count = len(speaker_duration)
    total = sum(speaker_duration.values()) or 1
    print(f"[Diarization] 감지된 화자 수: {speaker_count}")

    if speaker_count < 2:
        return {"speaker_count": speaker_count, "interviewee_segments": []}

    interviewee = max(speaker_duration, key=lambda s: speaker_duration[s])
    for spk, dur in sorted(speaker_duration.items(), key=lambda x: -x[1]):
        flag = " ← 면접자" if spk == interviewee else ""
        print(f"  {spk}: {dur:.1f}초 ({dur/total*100:.0f}%){flag}")

    segs = sorted(speaker_segments[interviewee], key=lambda x: x["start"])
    return {"speaker_count": speaker_count, "interviewee_segments": segs}


def slice_words_to_segments(
    words_info: list[dict],
    segments: list[dict],
    tolerance: float = 0.1,
) -> list[dict]:
    """
    Whisper words_info에서 면접자 발화 구간에 해당하는 단어만 필터링합니다.

    Parameters
    ----------
    words_info : list[dict]
        Whisper word-level timestamps
    segments : list[dict]
        get_interviewee_segments() 반환값
    tolerance : float
        구간 경계 허용 오차(초)

    Returns
    -------
    list[dict]
        면접자 구간에 속하는 words_info 부분집합
    """
    if not segments:
        return words_info  # 화자 분리 실패 시 전체 반환

    filtered = []
    for word in words_info:
        word_mid = (word["start"] + word["end"]) / 2
        for seg in segments:
            if seg["start"] - tolerance <= word_mid <= seg["end"] + tolerance:
                filtered.append(word)
                break
    return filtered