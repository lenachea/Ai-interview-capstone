"""
api.py
------
비언어모듈의 외부 호출용 clean API.
backend/main.py에서 import nonverbal_api 로 사용합니다.

analyze_nonverbal(video_path) 하나만 호출하면
시선·표정·자세 분석 결과와 scorer.py 용 점수, eval_model 추론용 raw feature를
모두 반환합니다.

내부 구현은 vision_features.py 로 옮겨졌다 — eval_model/scripts/extract_features.py
(36개 학습 영상 feature 추출)와 완전히 동일한 코드를 써서, 학습에 쓴 feature와
실서비스 추론에 쓰는 feature가 어긋나지 않게 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def analyze_nonverbal(video_path: str, sample_fps: float = 2.0) -> dict:
    """
    영상 파일 경로를 받아 비언어 분석 결과를 반환합니다.

    Parameters
    ----------
    video_path : str
        원본 영상 파일 경로 (mp4 등). 프레임을 이 함수 내부에서 직접 샘플링합니다.
    sample_fps : float
        초당 몇 프레임을 분석할지 (기본 2.0 — eval_model 학습 때와 동일).

    Returns
    -------
    {
        "raw_features": {...},   # eval_model 추론용 원본 지표 (gaze_*, emo_*, posture_*)

        # scorer.py 용 점수 (0~100 or None) — 기존 호출부 하위호환
        "eye_contact_score":       int | None,
        "face_stability_score":    int | None,
        "face_diversity_score":    int | None,
        "posture_stability_score": int | None,

        # 프론트엔드 상세 표시용
        "gaze_summary":       {...},
        "expression_summary": {...},
        "posture_summary":    {...},

        # 감점 구간 타임스탬프 (프론트엔드 구간 카드용)
        "gaze_deductions":    [{"start": float, "end": float, "direction": str}, ...],
        "expression_deductions": [{"start": float, "end": float, "emotion": str}, ...],
        "posture_deductions": [{"sec": float, "confidence": float}, ...],

        "status": "success" | "partial" | "failed",
        "errors": [...],
    }
    """
    from vision_features import analyze_video
    return analyze_video(video_path, sample_fps=sample_fps)
