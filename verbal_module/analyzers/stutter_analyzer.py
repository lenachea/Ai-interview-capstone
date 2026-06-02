"""
analyzers/stutter_analyzer.py
------------------------------
말 더듬/반복 탐지 담당 모듈.
"""

from __future__ import annotations
import re

from models import MetricDetail


def detect_stutters(
    words_info: list[dict],
    okt=None,
    window_size: int = 2,
    time_limit: float = 2.5,
) -> MetricDetail:
    """
    동일 단어가 짧은 시간 내 연속 반복될 때만 더듬음으로 판정합니다.

    Parameters
    ----------
    words_info : list[dict]
        [{"word", "start", "end"}, ...]
    okt : 미사용 (호환성 유지)
    window_size : int
        직전 몇 개 단어까지 비교할지
    time_limit : float
        이 시간(초) 이상 떨어진 반복은 더듬기로 보지 않음
    """
    stutter_ts = []
    flagged = set()

    for i in range(1, len(words_info)):
        if i in flagged:
            continue
        word_i = re.sub(r"[^\w]", "", words_info[i]["word"]).strip()
        if len(word_i) < 2:
            continue

        for j in range(max(0, i - window_size), i):
            word_j = re.sub(r"[^\w]", "", words_info[j]["word"]).strip()
            if len(word_j) < 2:
                continue
            if words_info[i]["start"] - words_info[j]["start"] > time_limit:
                continue
            if word_i == word_j:
                stutter_ts.append({
                    "time": round(words_info[i]["start"], 2),
                    "word": words_info[i]["word"],
                    "repeated_from": words_info[j]["word"],
                })
                flagged.add(i)
                break

    return MetricDetail(count=len(stutter_ts), occurrences=stutter_ts)
