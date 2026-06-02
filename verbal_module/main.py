"""
main.py
-------
각 모듈을 조합하여 분석 결과를 JSON으로 저장합니다.

실행:
    python main.py
또는 파일명 지정:
    python main.py ckmk_a_ict_f_e_156000
"""

from __future__ import annotations

import json
import os
import sys

from konlpy.tag import Okt

from ngram_model import NgramLanguageModel, make_tokenizer
from filler_detector import FillerDetector
from models import AnalysisReport, RawData, InterviewMetrics

from analyzers import transcribe, load_model, detect_fillers, detect_stutters, detect_pauses
from analyzers import calc_speech_rate, get_interviewee_segments, slice_words_to_segments,analyze_volume, load_pipeline


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

from dotenv import load_dotenv
load_dotenv()


WHISPER_MODEL_SIZE = "small"
CORPUS_PATH = "data/corpus.txt"          # 경로 지정 시 train_from_file 사용. 예: "data/corpus.txt"
MODEL_PATH  = "models/ngram_model.pkl"
PAUSE_THRESHOLD = 2.0
STUTTER_WINDOW = 3
STUTTER_TIME_LIMIT = 5.0
FILLER_THRESHOLD = 0.35

INPUT_DIR = "data/wavs"
OUTPUT_DIR = "results"

HF_TOKEN          = os.environ.get("HF_TOKEN", "")   # .env 또는 환경변수 권장
USE_DIARIZATION   = bool(HF_TOKEN)                   # 토큰 없으면 자동 비활성화

DEFAULT_CORPUS = [
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


 
# ---------------------------------------------------------------------------
# 초기화
# ---------------------------------------------------------------------------
 
def build_detector() -> FillerDetector:
    tokenize_fn, tagger = make_tokenizer(analyzer="okt", use_pos=False)
 
    if os.path.exists(MODEL_PATH):
        lm = NgramLanguageModel.load(MODEL_PATH)
        # 로드된 모델에 tokenize_fn 재주입 (pickle은 함수를 저장 못함)
        lm._tokenize = tokenize_fn
    else:
        lm = NgramLanguageModel(n=3, k=0.1, tokenize_fn=tokenize_fn)
        if CORPUS_PATH and os.path.exists(CORPUS_PATH):
            lm.train_from_file(CORPUS_PATH)
            print(f"[LM] 코퍼스 로드: {CORPUS_PATH}")
        else:
            lm.train(DEFAULT_CORPUS)
            print("[LM] 내장 코퍼스로 학습")
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        lm.save(MODEL_PATH)
 
    return FillerDetector(lm=lm, tagger=tagger, threshold=FILLER_THRESHOLD)
 
 
# ---------------------------------------------------------------------------
# 분석 파이프라인
# ---------------------------------------------------------------------------
 
def analyze(
    audio_path: str,
    whisper_model,
    detector: FillerDetector,
    okt: Okt,
    diarization_pipeline=None,
) -> dict:
    try:
        # 1. STT
        full_text, words_info = transcribe(whisper_model, audio_path)
        if not words_info:
            return AnalysisReport.failure("No speech detected").to_dict()
 
        # 2. 화자 분리 → 면접자 구간 추출
        interviewee_segments = []
        if diarization_pipeline is not None:
            try:
                interviewee_segments = get_interviewee_segments(
                    audio_path, diarization_pipeline
                )
                # Whisper words_info를 면접자 구간으로 필터링
                words_info = slice_words_to_segments(words_info, interviewee_segments)
                print(f"[Diarization] 면접자 단어 수: {len(words_info)}")
            except Exception as e:
                print(f"[Diarization] 실패, 전체 음성으로 진행: {e}")
 
        if not words_info:
            return AnalysisReport.failure("No interviewee speech detected").to_dict()
 
        # 3. 기본 지표
        total = round(words_info[-1]["end"] - words_info[0]["start"], 2)
        pure  = round(sum(w["end"] - w["start"] for w in words_info), 2)
 
        # 4. 음량 분석 (면접자 구간만)
        volume = analyze_volume(audio_path, interviewee_segments)
 
        report = AnalysisReport(
            raw_data=RawData(
                transcript=full_text,
                total_duration_sec=total,
                pure_speech_time_sec=pure,
            ),
            metrics=InterviewMetrics(
                filler_word     =detect_fillers(full_text, words_info, detector),
                stuttering      =detect_stutters(words_info, okt, STUTTER_WINDOW, STUTTER_TIME_LIMIT),
                long_pauses     =detect_pauses(words_info, PAUSE_THRESHOLD),
                speech_rate     =calc_speech_rate(full_text, words_info),
                volume_stability=AnalysisReport.empty_volume().__class__(**volume),
            ),
            status="success",
        )
        return report.to_dict()
 
    except Exception as e:
        return AnalysisReport.failure(str(e)).to_dict()
 
 
# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    filename   = sys.argv[1] if len(sys.argv) > 1 else "ckmk_a_ict_f_e_156000"
    audio_path = os.path.join(INPUT_DIR, f"{filename}.wav")
 
    print(f"[시작] {audio_path}")
    print(f"[화자 분리] {'활성화' if USE_DIARIZATION else '비활성화 (HF_TOKEN 없음)'}")
 
    # 모델 로드
    whisper_model = load_model(WHISPER_MODEL_SIZE)
    detector      = build_detector()
    okt           = Okt()
    diarization_pipeline = load_pipeline(HF_TOKEN) if USE_DIARIZATION else None
 
    result = analyze(audio_path, whisper_model, detector, okt, diarization_pipeline)
 
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{filename}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
 
    print(f"[완료] {output_path}")
    if result.get("status") == "failed":
        print(f"[오류] {result.get('error_message')}")
 