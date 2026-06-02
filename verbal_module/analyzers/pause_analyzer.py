"""
analyzers/pause_analyzer.py
----------------------------
긴 침묵 구간 탐지 담당 모듈.
"""

from __future__ import annotations
from models import MetricDetail


def detect_pauses(
    words_info: list[dict],
    pause_threshold: float = 2.0,
) -> MetricDetail:
    """
    Parameters
    ----------
    words_info : list[dict]
        [{"word", "start", "end"}, ...]
    pause_threshold : float
        침묵 판정 기준(초)

    Returns
    -------
    MetricDetail
    """
    pause_ts = []
    for i in range(1, len(words_info)):
        gap = words_info[i]["start"] - words_info[i - 1]["end"]
        if gap >= pause_threshold:
            pause_ts.append({
                "start": round(words_info[i - 1]["end"], 2),
                "end": round(words_info[i]["start"], 2),
                "duration": round(gap, 2),
            })
    return MetricDetail(count=len(pause_ts), occurrences=pause_ts)
