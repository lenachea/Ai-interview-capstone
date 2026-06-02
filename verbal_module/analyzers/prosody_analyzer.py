"""
analyzers/prosody_analyzer.py
------------------------------
librosa 기반 음량 안정성 분석 모듈.

판정 기준
---------
cv < 0.75         → "안정적"
0.75 <= cv < 0.85 → "보통"
cv >= 0.85        → "불안정"
mean < 0.015      → "너무 작음" (위 판정에 추가)
"""

from __future__ import annotations
import numpy as np

DEFAULT_CV_STABLE    = 0.75
DEFAULT_CV_UNSTABLE  = 0.85
DEFAULT_VOLUME_MIN   = 0.015
DEFAULT_FRAME_LENGTH = 2048
DEFAULT_HOP_LENGTH   = 512


def analyze_volume(
    audio_path: str,
    interviewee_segments: list[dict],
    cv_stable: float   = DEFAULT_CV_STABLE,
    cv_unstable: float = DEFAULT_CV_UNSTABLE,
    volume_min: float  = DEFAULT_VOLUME_MIN,
    frame_length: int  = DEFAULT_FRAME_LENGTH,
    hop_length: int    = DEFAULT_HOP_LENGTH,
) -> dict:
    """
    Parameters
    ----------
    audio_path : str
    interviewee_segments : list[dict]
        [{"start": float, "end": float}, ...] 빈 리스트면 전체 분석
    cv_stable : float
        이 값 미만이면 "안정적"
    cv_unstable : float
        이 값 이상이면 "불안정" (사이는 "보통")
    volume_min : float
        RMS 평균 최솟값 ("너무 작음" 기준)

    Returns
    -------
    dict
    """
    import librosa

    y, sr = librosa.load(audio_path, sr=None, mono=True)

    # 면접자 구간만 이어붙이기
    if interviewee_segments:
        chunks = []
        for seg in interviewee_segments:
            s = max(0, int(seg["start"] * sr))
            e = min(len(y), int(seg["end"] * sr))
            if e > s:
                chunks.append(y[s:e])
        y_target = np.concatenate(chunks) if chunks else y
    else:
        y_target = y

    rms = librosa.feature.rms(
        y=y_target,
        frame_length=frame_length,
        hop_length=hop_length,
    )[0]

    rms_active = rms[rms > 0.001]  # 무음 구간 제외
    if len(rms_active) == 0:
        return _empty_result()

    rms_mean = float(np.mean(rms_active))
    rms_std  = float(np.std(rms_active))
    cv       = rms_std / rms_mean if rms_mean > 0 else 0.0

    is_loud_enough = rms_mean >= volume_min

    # 안정성 판정
    if cv < cv_stable:
        stability = "안정적"
    elif cv < cv_unstable:
        stability = "보통"
    else:
        stability = "불안정"

    # 음량 작으면 판정에 추가
    if not is_loud_enough:
        label = f"{stability}+작음" if stability != "안정적" else "너무 작음"
    else:
        label = stability

    return {
        "rms_mean":       round(rms_mean, 5),
        "rms_std":        round(rms_std,  5),
        "cv":             round(cv,       4),
        "label":          label,
        "is_stable":      cv < cv_unstable,   # 보통 이하면 stable로 간주
        "is_loud_enough": is_loud_enough,
    }


def _empty_result() -> dict:
    return {
        "rms_mean": 0.0, "rms_std": 0.0, "cv": 0.0,
        "label": "분석 불가", "is_stable": False, "is_loud_enough": False,
    }