"""
analyzers/speech_rate.py
-------------------------
말하기 속도(SPM) 계산 담당 모듈.
"""

from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))

from models import SpeechRate

try:
    from scorer import SPM_SLOW, SPM_FAST
except ImportError:
    SPM_SLOW, SPM_FAST = 270.0, 350.0


def calc_speech_rate(
    full_text: str,
    words_info: list[dict],
    slow_limit: float = SPM_SLOW,
    fast_limit: float = SPM_FAST,
) -> SpeechRate:
    """
    Parameters
    ----------
    full_text : str
        STT 전체 텍스트 (음절 수 계산용)
    words_info : list[dict]
        [{"word", "start", "end"}, ...]
    slow_limit : float
        이 값 미만이면 '느림'
    fast_limit : float
        이 값 초과이면 '빠름'

    Returns
    -------
    SpeechRate
    """
    pure_time = sum(
        w["end"] - w["start"]
        for w in words_info
        if w.get("end") is not None and w.get("start") is not None
    )
    syllables = len(full_text.replace(" ", ""))
    spm = round(syllables / (pure_time / 60), 2) if pure_time > 0 else 0.0
    label = "적절" if slow_limit <= spm <= fast_limit else "빠름" if spm > fast_limit else "느림"
    return SpeechRate(spm=round(spm, 1), label=label)
