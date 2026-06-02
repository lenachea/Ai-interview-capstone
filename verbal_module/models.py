"""
models.py
---------
프로젝트 전체에서 공유하는 데이터 클래스 정의.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class MetricDetail:
    count: int
    occurrences: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SpeechRate:
    spm: float
    label: str


@dataclass
class VolumeStability:
    rms_mean: float
    rms_std: float
    cv: float
    label: str            # "안정적" | "불안정" | "너무 작음" | "불안정+작음"
    is_stable: bool
    is_loud_enough: bool


@dataclass
class InterviewMetrics:
    filler_word:      MetricDetail
    stuttering:       MetricDetail
    long_pauses:      MetricDetail
    speech_rate:      SpeechRate
    volume_stability: VolumeStability


@dataclass
class RawData:
    transcript:          str
    total_duration_sec:  float
    pure_speech_time_sec: float


@dataclass
class AnalysisReport:
    raw_data: RawData
    metrics:  InterviewMetrics
    status:        str = "success"
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def empty_volume() -> VolumeStability:
        return VolumeStability(
            rms_mean=0.0, rms_std=0.0, cv=0.0,
            label="분석 불가", is_stable=False, is_loud_enough=False,
        )

    @staticmethod
    def empty_metrics() -> InterviewMetrics:
        empty = MetricDetail(count=0, occurrences=[])
        return InterviewMetrics(
            filler_word=empty,
            stuttering=empty,
            long_pauses=empty,
            speech_rate=SpeechRate(spm=0.0, label="알 수 없음"),
            volume_stability=AnalysisReport.empty_volume(),
        )

    @staticmethod
    def failure(reason: str) -> "AnalysisReport":
        return AnalysisReport(
            raw_data=RawData("", 0.0, 0.0),
            metrics=AnalysisReport.empty_metrics(),
            status="failed",
            error_message=reason,
        )