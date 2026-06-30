"""
scorer.py
---------
언어모듈 + 비언어모듈 분석 결과를 바탕으로 평가 점수를 계산합니다.

항목:
  발화속도      - spm 구간 점수 + 긴침묵 비율 점수 평균
  말하기안정성  - 더듬음·filler 비율 + 음량 cv, 3개 지표 평균
  표정안정성    - 비언어모듈 (미구현 → None)
  표정다양성    - 비언어모듈 (미구현 → None)
  자세안정성    - 비언어모듈 (미구현 → None)
  시선처리      - 비언어모듈 (미구현 → None)
"""
from __future__ import annotations
from typing import Optional


# ── SPM 기준 (speech_rate.py와 공유) ─────────────────────────────────────────
SPM_SLOW  = 270   # 미만: 느림
SPM_FAST  = 350   # 초과: 빠름


# ── 발화속도: spm 점수 + 긴침묵 점수 평균 ────────────────────────────────────

def _spm_score(spm: float) -> int:
    if SPM_SLOW <= spm <= SPM_FAST:
        return 100
    if (230 <= spm < SPM_SLOW) or (SPM_FAST < spm <= 390):
        return 80
    if (190 <= spm < 230) or (390 < spm <= 430):
        return 60
    return 40


def _speech_rate_score(speech_rate: dict, long_pauses: dict, pure_time: float) -> int:
    spm_score   = _spm_score(speech_rate.get("spm") or 0)
    pause_score = _ratio_score(long_pauses.get("count", 0), pure_time)
    return round((spm_score + pause_score) / 2)


# ── 말하기안정성: 비율 기반 지표 2개(더듬음·filler) + cv 기반 음량 1개 ────────

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


def _stability_score(metrics: dict, pure_time: float) -> int:
    stutter = _ratio_score(metrics.get("stuttering",  {}).get("count", 0), pure_time)
    filler  = _ratio_score(metrics.get("filler_word", {}).get("count", 0), pure_time)
    volume  = _volume_cv_score(metrics.get("volume_stability", {}).get("cv", 0.0))
    return round((stutter + filler + volume) / 3)


# ── 답변별 점수 집계 ─────────────────────────────────────────────────────────

_SCORE_KEYS = ["발화속도", "말하기안정성", "표정안정성", "표정다양성", "자세안정성", "시선처리"]


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
        result["표정안정성"] = nonverbal_analysis.get("face_stability_score")
        result["표정다양성"] = nonverbal_analysis.get("face_diversity_score")
        result["자세안정성"] = nonverbal_analysis.get("posture_stability_score")
        result["시선처리"]   = nonverbal_analysis.get("eye_contact_score")

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
    dict keys: 표정안정성, 표정다양성, 자세안정성, 시선처리, 발화속도, 말하기안정성, 총점
    """
    metrics   = language_analysis.get("metrics", {})
    pure_time = language_analysis.get("raw_data", {}).get("pure_speech_time_sec", 0) or 0

    scores: dict[str, Optional[int]] = {
        "표정안정성":   None,
        "표정다양성":   None,
        "자세안정성":   None,
        "시선처리":     None,
        "발화속도":     _speech_rate_score(
                            metrics.get("speech_rate", {}),
                            metrics.get("long_pauses", {}),
                            pure_time,
                        ),
        "말하기안정성": _stability_score(metrics, pure_time),
    }

    if nonverbal_analysis and nonverbal_analysis.get("status") != "failed":
        scores.update({
            "표정안정성": nonverbal_analysis.get("face_stability_score"),
            "표정다양성": nonverbal_analysis.get("face_diversity_score"),
            "자세안정성": nonverbal_analysis.get("posture_stability_score"),
            "시선처리":   nonverbal_analysis.get("eye_contact_score"),
        })

    valid = [v for v in scores.values() if v is not None]
    scores["총점"] = round(sum(valid) / len(valid)) if valid else 0

    return scores
