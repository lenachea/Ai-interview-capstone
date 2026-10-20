"""
scorer.py
---------
언어모듈 + 비언어모듈 분석 결과를 바탕으로 평가 점수를 계산합니다.
eval_model(ML)이 쓰이지 않을 때(모델 파일 없음/추론 실패)의 휴리스틱 fallback이며,
키 구성은 eval_model의 7개 항목과 1:1로 맞춘다 (main.py의 _ml_pred_to_scores와 동일 스키마).

항목:
  발화속도    - spm 구간 점수
  음성명확성  - 더듬음 비율 + 음량 cv, 2개 지표 평균
  유창성침묵  - 긴침묵 비율 점수
  습관어      - 습관어(filler) 비율 점수
  표정안정성  - 비언어모듈 face_stability_score
  자세안정성  - 비언어모듈 posture_stability_score
  시선처리    - 비언어모듈 eye_contact_score
"""
from __future__ import annotations
from typing import Optional


# ── SPM 기준 (speech_rate.py와 공유) ─────────────────────────────────────────
SPM_SLOW  = 270   # 미만: 느림
SPM_FAST  = 350   # 초과: 빠름


# ── 발화속도: spm 구간 점수 ──────────────────────────────────────────────────

def _spm_score(spm: float) -> int:
    if SPM_SLOW <= spm <= SPM_FAST:
        return 100
    if (230 <= spm < SPM_SLOW) or (SPM_FAST < spm <= 390):
        return 80
    if (190 <= spm < 230) or (390 < spm <= 430):
        return 60
    return 40


# ── 비율 기반 지표 공통 (더듬음·습관어·긴침묵) ───────────────────────────────

def _ratio_score(count: int, pure_time: float) -> int:
    """횟수 / 순수발화시간(초) 비율 → 점수"""
    if pure_time <= 0:
        return 100
    ratio = count / pure_time
    if ratio == 0:
        return 100
    if ratio <= 0.03:
        return 80
    if ratio <= 0.06:
        return 60
    return 40


def _volume_cv_score(cv: float) -> int:
    if cv <= 0.3:
        return 100
    if cv <= 0.6:
        return 80
    if cv <= 0.9:
        return 60
    return 40


def _clarity_score(metrics: dict, pure_time: float) -> int:
    """음성명확성: 더듬음 비율 + 음량 안정성(cv), 2개 지표 평균."""
    stutter = _ratio_score(metrics.get("stuttering", {}).get("count", 0), pure_time)
    volume  = _volume_cv_score(metrics.get("volume_stability", {}).get("cv", 0.0))
    return round((stutter + volume) / 2)


# ── 답변별 점수 집계 ─────────────────────────────────────────────────────────

_SCORE_KEYS = ["발화속도", "음성명확성", "유창성침묵", "습관어",
               "시선처리", "표정안정성", "자세안정성"]


def aggregate_scores(
    seg_scores: list[dict],
    nonverbal_analysis: Optional[dict] = None,
) -> dict:
    """
    답변별 calc_scores() 결과를 평균하여 전체 점수를 반환합니다.
    nonverbal_analysis가 있으면 비언어 점수를 덮어씁니다.
    """
    result: dict[str, Optional[int]] = {}
    for key in _SCORE_KEYS:
        vals = [s[key] for s in seg_scores if s.get(key) is not None]
        result[key] = round(sum(vals) / len(vals)) if vals else None

    if nonverbal_analysis and nonverbal_analysis.get("status") != "failed":
        result["시선처리"]   = nonverbal_analysis.get("eye_contact_score")
        result["표정안정성"] = nonverbal_analysis.get("face_stability_score")
        result["자세안정성"] = nonverbal_analysis.get("posture_stability_score")

    valid = [v for v in result.values() if v is not None]
    result["총점"] = round(sum(valid) / len(valid)) if valid else 0
    return result


# ── 최종 점수 계산 ───────────────────────────────────────────────────────────

def calc_scores(
    language_analysis: dict,
    nonverbal_analysis: Optional[dict] = None,
) -> dict:
    """
    Returns
    -------
    dict keys: 발화속도, 음성명확성, 유창성침묵, 습관어, 시선처리, 표정안정성, 자세안정성, 총점
    """
    metrics   = language_analysis.get("metrics", {})
    pure_time = language_analysis.get("raw_data", {}).get("pure_speech_time_sec", 0) or 0

    scores: dict[str, Optional[int]] = {
        "발화속도":   _spm_score(metrics.get("speech_rate", {}).get("spm") or 0),
        "음성명확성": _clarity_score(metrics, pure_time),
        "유창성침묵": _ratio_score(metrics.get("long_pauses", {}).get("count", 0), pure_time),
        "습관어":     _ratio_score(metrics.get("filler_word", {}).get("count", 0), pure_time),
        "시선처리":   None,
        "표정안정성": None,
        "자세안정성": None,
    }

    if nonverbal_analysis and nonverbal_analysis.get("status") != "failed":
        scores.update({
            "시선처리":   nonverbal_analysis.get("eye_contact_score"),
            "표정안정성": nonverbal_analysis.get("face_stability_score"),
            "자세안정성": nonverbal_analysis.get("posture_stability_score"),
        })

    valid = [v for v in scores.values() if v is not None]
    scores["총점"] = round(sum(valid) / len(valid)) if valid else 0

    return scores
