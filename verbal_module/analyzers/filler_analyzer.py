"""
analyzers/filler_analyzer.py
-----------------------------
Filler word 탐지 담당 모듈.
FillerDetector(N-gram + KoNLPy)를 래핑합니다.
"""

from __future__ import annotations
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filler_detector import FillerDetector
from models import MetricDetail


# 단순 표면형으로 잡을 multi-word filler
# (FillerDetector는 단일 토큰 단위이므로 별도 처리)
MULTI_WORD_FILLERS = {"그래서 저", "또 그", "또 저", "좀 더"}


def detect_fillers(
    full_text: str,
    words_info: list[dict],
    detector: FillerDetector,
) -> MetricDetail:
    """
    Parameters
    ----------
    full_text : str
        Whisper STT 전체 텍스트
    words_info : list[dict]
        [{"word", "start", "end"}, ...]
    detector : FillerDetector
        main에서 초기화하여 주입

    Returns
    -------
    MetricDetail
    """
    # 단일 토큰 filler (N-gram + KoNLPy)
    result = detector.detect(full_text, word_timestamps=words_info)
    occurrences = [
    {
        "time": round(f.start_time, 2) if f.start_time is not None else None,
        "word": f.token,
        "pos": f.pos,
        "score": round(f.final_score, 2),
    }
    for f in result.fillers
    ]

    # multi-word filler (bigram 슬라이딩 윈도우)
    for i in range(len(words_info) - 1):
        w1 = re.sub(r"[^\w\s]", "", words_info[i]["word"]).strip()
        w2 = re.sub(r"[^\w\s]", "", words_info[i + 1]["word"]).strip()
        bigram = f"{w1} {w2}"
        if bigram in MULTI_WORD_FILLERS:
            occurrences.append({
                "time": round(words_info[i]["start"], 2),
                "word": bigram,
                "pos": "multi-word",
                "score": 1.0,
            })

    occurrences.sort(key=lambda x: x["time"] or 0)
    return MetricDetail(count=len(occurrences), occurrences=occurrences)
