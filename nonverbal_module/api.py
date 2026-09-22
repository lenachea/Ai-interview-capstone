"""
api.py
------
비언어모듈의 외부 호출용 clean API.
backend/main.py에서 import nonverbal_api 로 사용합니다.

analyze_nonverbal(frames_dir) 하나만 호출하면
시선·표정·자세 분석 결과와 scorer.py 용 점수를 모두 반환합니다.
"""
from __future__ import annotations

import os
import sys
import numpy as np
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def analyze_nonverbal(frames_dir: str) -> dict:
    """
    프레임 디렉토리를 받아 비언어 분석 결과를 반환합니다.

    Parameters
    ----------
    frames_dir : str
        backend/preprocessor.extract_frames()가 저장한 JPEG 프레임 폴더 경로

    Returns
    -------
    {
        # scorer.py 용 점수 (0~100 or None)
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
        "posture_deductions": [{"sec": int, "confidence": float}, ...],

        "status": "success" | "partial" | "failed",
        "errors": [...],
    }
    """
    errors = []

    # ── 1. 시선 분석 ─────────────────────────────────────────────────────────
    gaze_summary = {}
    gaze_deductions = []
    eye_contact_score = None
    try:
        from eye_tracker import analyze_frames_gaze, summarize_gaze, MODEL_PATH as _GAZE_MODEL_PATH
        print(f"[Nonverbal/gaze] model path: {_GAZE_MODEL_PATH}")
        print(f"[Nonverbal/gaze] model exists: {os.path.exists(_GAZE_MODEL_PATH)}")
        gaze_log    = analyze_frames_gaze(frames_dir, fps=1)
        gaze_summary = summarize_gaze(gaze_log)

        center_ratio = gaze_summary.get("gaze_ratio", 0)
        if center_ratio >= 0.8:
            eye_contact_score = 100
        elif center_ratio >= 0.6:
            eye_contact_score = 80
        elif center_ratio >= 0.4:
            eye_contact_score = 60
        else:
            eye_contact_score = 40

        gaze_deductions = gaze_summary.get("deviated_segments", [])
    except Exception as e:
        errors.append(f"gaze: {e}")

    # ── 2. 표정 분석 ─────────────────────────────────────────────────────────
    expression_summary = {}
    face_stability_score = None
    face_diversity_score = None
    try:
        from emotion_classifier import analyze_expression_frames
        expression_summary   = analyze_expression_frames(frames_dir)
        face_stability_score = expression_summary.get("stability_score")
        face_diversity_score = expression_summary.get("diversity_score")
    except Exception as e:
        errors.append(f"expression: {e}")

    # ── 3. 자세 분석 ─────────────────────────────────────────────────────────
    posture_summary = {}
    posture_deductions = []
    posture_stability_score = None
    try:
        import cv2
        import glob as _glob
        from upperbody_movement import PostureAnalyzer

        frame_files = sorted(_glob.glob(os.path.join(frames_dir, "*.jpg")))
        if not frame_files:
            frame_files = sorted(_glob.glob(os.path.join(frames_dir, "*.png")))

        if frame_files:
            analyzer = PostureAnalyzer()

            # 초반 3프레임으로 캘리브레이션
            for f in frame_files[:3]:
                frame = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    analyzer.feed_calibration(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            analyzer.finalize_calibration()

            slouch_count = 0
            upright_count = 0
            records = []

            for sec, f in enumerate(frame_files):
                frame = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                res = analyzer.analyze(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                label = res["label"]
                if label == "slouched":
                    slouch_count += 1
                    posture_deductions.append({
                        "sec":        sec,
                        "confidence": res["confidence"],
                    })
                elif label == "upright":
                    upright_count += 1
                records.append(label)

            analyzer.close()

            total = slouch_count + upright_count
            slouch_ratio = slouch_count / total if total > 0 else 0.0

            if slouch_ratio <= 0.1:
                posture_stability_score = 100
            elif slouch_ratio <= 0.25:
                posture_stability_score = 80
            elif slouch_ratio <= 0.45:
                posture_stability_score = 60
            else:
                posture_stability_score = 40

            if slouch_ratio <= 0.1:
                posture_feedback = "자세가 전반적으로 안정적입니다."
            elif slouch_ratio <= 0.3:
                posture_feedback = f"구부정한 자세가 {slouch_count}회 감지되었습니다. 허리를 펴고 어깨를 편 자세를 유지해보세요."
            else:
                posture_feedback = f"구부정한 자세가 자주 나타납니다({int(slouch_ratio*100)}%). 면접 중 바른 자세를 의식적으로 유지해보세요."

            posture_summary = {
                "slouch_count":   slouch_count,
                "upright_count":  upright_count,
                "slouch_ratio":   round(slouch_ratio, 3),
                "feedback":       posture_feedback,
            }
    except Exception as e:
        errors.append(f"posture: {e}")

    # ── 최종 status ──────────────────────────────────────────────────────────
    scores = [eye_contact_score, face_stability_score,
              face_diversity_score, posture_stability_score]
    success_count = sum(1 for s in scores if s is not None)

    if success_count == 0:
        status = "failed"
    elif success_count < len(scores):
        status = "partial"
    else:
        status = "success"

    return {
        "eye_contact_score":       eye_contact_score,
        "face_stability_score":    face_stability_score,
        "face_diversity_score":    face_diversity_score,
        "posture_stability_score": posture_stability_score,
        "gaze_summary":            gaze_summary,
        "expression_summary":      expression_summary,
        "posture_summary":         posture_summary,
        "gaze_deductions":         gaze_deductions,
        "posture_deductions":      posture_deductions,
        "status":                  status,
        "errors":                  errors,
    }
