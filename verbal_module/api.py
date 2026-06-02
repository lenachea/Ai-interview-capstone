"""
api.py
------
언어모듈의 외부 호출용 clean API.
절대 경로를 사용하여 어느 디렉토리에서 실행해도 동작합니다.
모델은 최초 호출 시 한 번만 로드(lazy loading)합니다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_DIR = Path(__file__).parent
if str(_DIR) not in sys.path:
    sys.path.append(str(_DIR))   # insert(0) 금지 — main 모듈 충돌 방지

# ── 설정 (절대 경로) ─────────────────────────────────────────────────────────
CORPUS_PATH        = str(_DIR / "data" / "corpus.txt")
MODEL_PATH         = str(_DIR / "models" / "ngram_model.pkl")
WHISPER_MODEL_SIZE = "medium"
PAUSE_THRESHOLD    = 2.0
STUTTER_WINDOW     = 3
STUTTER_TIME_LIMIT = 5.0
FILLER_THRESHOLD   = 0.35

_DEFAULT_CORPUS = [
    "저는 개발자입니다",
    "그 프로젝트를 맡았습니다",
    "오늘 날씨가 정말 좋네요",
    "회의 시간이 변경되었습니다",
    "프로젝트 일정을 다시 검토해야 합니다",
    "보고서 초안을 내일까지 제출해 주세요",
    "데이터 분석 결과를 공유하겠습니다",
    "팀원들과 협의 후 결정하겠습니다",
    "어 오늘 음 날씨가 좋네요",
    "그 뭐 저 일정이 어 변경되었습니다",
    "음 그러니까 보고서를 뭐 내일까지 제출해야 합니다",
]

# ── Lazy globals ─────────────────────────────────────────────────────────────
_whisper_model = None
_detector      = None
_okt           = None
_initialized   = False


def _init():
    global _whisper_model, _detector, _okt, _initialized
    if _initialized:
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(str(_DIR / ".env"))
    except ImportError:
        pass

    from konlpy.tag import Okt
    from ngram_model import NgramLanguageModel, make_tokenizer
    from filler_detector import FillerDetector
    from analyzers import load_model

    _whisper_model = load_model(WHISPER_MODEL_SIZE)
    _okt = Okt()

    tokenize_fn, tagger = make_tokenizer(analyzer="okt", use_pos=False)
    if os.path.exists(MODEL_PATH):
        lm = NgramLanguageModel.load(MODEL_PATH)
        lm._tokenize = tokenize_fn
    else:
        lm = NgramLanguageModel(n=3, k=0.1, tokenize_fn=tokenize_fn)
        if os.path.exists(CORPUS_PATH):
            lm.train_from_file(CORPUS_PATH)
        else:
            lm.train(_DEFAULT_CORPUS)
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        lm.save(MODEL_PATH)

    _detector = FillerDetector(lm=lm, tagger=tagger, threshold=FILLER_THRESHOLD)
    _initialized = True


def transcribe_file(audio_path: str) -> tuple[str, list[dict], list[dict]]:
    """전체 오디오 STT만 실행합니다. (full_text, words_info, segments_info) 반환."""
    _init()
    from analyzers.transcriber import transcribe_with_segments
    return transcribe_with_segments(_whisper_model, audio_path)


def analyze_from_words(
    words_info: list[dict],
    audio_path: str,
    answer_segment: dict,
) -> dict:
    """
    이미 STT된 words_info에서 특정 답변 구간만 분석합니다.
    answer_segment: {"start": float, "end": float}
    """
    _init()

    from analyzers import (
        detect_fillers, detect_stutters, detect_pauses,
        calc_speech_rate, analyze_volume, slice_words_to_segments,
    )
    from models import AnalysisReport, RawData, InterviewMetrics, VolumeStability

    try:
        segments = [answer_segment]
        seg_words = slice_words_to_segments(words_info, segments)

        if not seg_words:
            return AnalysisReport.failure("No words in segment").to_dict()

        valid = [w for w in seg_words
                 if w.get("start") is not None and w.get("end") is not None]
        if not valid:
            return AnalysisReport.failure("No valid word timestamps").to_dict()

        total     = round(valid[-1]["end"] - valid[0]["start"], 2)
        pure      = round(sum(w["end"] - w["start"] for w in valid), 2)
        full_text = " ".join(w["word"] for w in seg_words if w.get("word"))

        volume_dict = analyze_volume(audio_path, segments)

        report = AnalysisReport(
            raw_data=RawData(
                transcript=full_text,
                total_duration_sec=total,
                pure_speech_time_sec=pure,
            ),
            metrics=InterviewMetrics(
                filler_word      =detect_fillers(full_text, seg_words, _detector),
                stuttering       =detect_stutters(seg_words, _okt, STUTTER_WINDOW, STUTTER_TIME_LIMIT),
                long_pauses      =detect_pauses(seg_words, PAUSE_THRESHOLD),
                speech_rate      =calc_speech_rate(full_text, seg_words),
                volume_stability =VolumeStability(**volume_dict),
            ),
            status="success",
        )
        return report.to_dict()

    except Exception as e:
        return AnalysisReport.failure(str(e)).to_dict()


def analyze_file(audio_path: str, hf_token: str = "") -> dict:
    """
    파일 경로로 분석 실행 후 결과 dict 반환.
    audio_path: 절대 경로 (mp4, mov, avi, mkv, wav 등 moviepy/librosa 지원 포맷)
    """
    _init()

    from models import AnalysisReport, RawData, InterviewMetrics, VolumeStability
    from analyzers import (
        transcribe, detect_fillers, detect_stutters, detect_pauses,
        calc_speech_rate, get_interviewee_segments, slice_words_to_segments,
        analyze_volume, load_pipeline,
    )

    try:
        full_text, words_info = transcribe(_whisper_model, audio_path)
        if not words_info:
            return AnalysisReport.failure("No speech detected").to_dict()

        interviewee_segments: list = []
        if hf_token:
            try:
                pipeline = load_pipeline(hf_token)
                interviewee_segments = get_interviewee_segments(audio_path, pipeline)
                words_info = slice_words_to_segments(words_info, interviewee_segments)
            except Exception as e:
                print(f"[Diarization] 실패, 전체 음성으로 진행: {e}")

        if not words_info:
            return AnalysisReport.failure("No interviewee speech detected").to_dict()

        total = round(words_info[-1]["end"] - words_info[0]["start"], 2)
        pure  = round(sum(w["end"] - w["start"] for w in words_info), 2)

        volume_dict = analyze_volume(audio_path, interviewee_segments)

        report = AnalysisReport(
            raw_data=RawData(
                transcript=full_text,
                total_duration_sec=total,
                pure_speech_time_sec=pure,
            ),
            metrics=InterviewMetrics(
                filler_word      =detect_fillers(full_text, words_info, _detector),
                stuttering       =detect_stutters(words_info, _okt, STUTTER_WINDOW, STUTTER_TIME_LIMIT),
                long_pauses      =detect_pauses(words_info, PAUSE_THRESHOLD),
                speech_rate      =calc_speech_rate(full_text, words_info),
                volume_stability =VolumeStability(**volume_dict),
            ),
            status="success",
        )
        return report.to_dict()

    except Exception as e:
        return AnalysisReport.failure(str(e)).to_dict()
