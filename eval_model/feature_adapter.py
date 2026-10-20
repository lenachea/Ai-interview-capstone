"""
feature_adapter.py
-------------------
backend/main.py가 이미 계산해둔 언어 분석 집계(agg_lang, verbal_module 출력)를
eval_model 학습 때 쓴 언어 feature 스키마(extract_features.py의
extract_language_features() 출력)로 변환한다.

비전 feature는 nonverbal_module/vision_features.py가 이미 같은 스키마로 뽑아주므로
여기서는 언어 쪽만 다루고, 마지막에 두 dict를 합쳐 inference.predict_scores()에
바로 넣을 수 있는 하나의 feature dict로 만든다.
"""
from __future__ import annotations


def language_features_from_agg(agg_lang: dict) -> dict:
    """
    Parameters
    ----------
    agg_lang : dict
        backend/main.py의 _aggregate() 반환값 (verbal_module 분석 결과를
        답변 전체에 대해 집계한 것). 아래 필드를 기대함:
          raw_data.total_duration_sec, raw_data.pure_speech_time_sec, raw_data.transcript
          metrics.filler_word.count
          metrics.stuttering.count
          metrics.long_pauses.count / occurrences[].duration(or start/end)
          metrics.speech_rate.spm
          metrics.volume_stability.rms_mean/rms_std/cv
    """
    metrics = agg_lang.get("metrics", {}) or {}
    raw = agg_lang.get("raw_data", {}) or {}

    total = float(raw.get("total_duration_sec") or 0.0)
    pure = float(raw.get("pure_speech_time_sec") or 0.0)
    minutes = max(total / 60.0, 1e-6)

    pauses = metrics.get("long_pauses", {}).get("occurrences", []) or []
    pause_durs = []
    for p in pauses:
        d = p.get("duration")
        if d is None and p.get("start") is not None and p.get("end") is not None:
            d = float(p["end"]) - float(p["start"])
        pause_durs.append(float(d or 0.0))

    volume = metrics.get("volume_stability", {}) or {}
    filler_count = int(metrics.get("filler_word", {}).get("count") or 0)
    stutter_count = int(metrics.get("stuttering", {}).get("count") or 0)

    return {
        "spm": float(metrics.get("speech_rate", {}).get("spm") or 0.0),
        "filler_count": filler_count,
        "filler_per_min": filler_count / minutes,
        "stutter_count": stutter_count,
        "stutter_per_min": stutter_count / minutes,
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


def combine(vision_raw_features: dict, agg_lang: dict) -> dict:
    """비전 raw feature + 언어 feature를 합쳐 inference.predict_scores()용 dict를 만든다."""
    features = dict(vision_raw_features or {})
    features.update(language_features_from_agg(agg_lang or {}))
    return features
