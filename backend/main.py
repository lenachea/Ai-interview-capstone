"""
main.py
-------
FastAPI 서버: 영상 → 오디오+프레임 분리 → 화자 분리 → 답변별 음성분석 + 비전분석 → 점수 계산

실행:
    cd backend
    uvicorn main:app --reload --port 8000

엔드포인트:
    POST /analyze                    영상 업로드 + 분석 시작
    GET  /results/{job_id}           분석 결과 조회
    GET  /history                    완료된 분석 기록 목록 (최신순)
    GET  /compare/{job_id}           현재·이전 결과 + 점수 차이 (업로드 분석 전용)
    GET  /audio-clip/{job_id}?start=&end=  감점 구간 오디오 클립
    GET  /realtime/questions         분야별 질문 목록
    POST /realtime/start             실시간/실전연습 세션 시작
    POST /realtime/{job_id}/finish   연속 녹화 영상 + 타임스탬프 업로드, 분석 시작
    GET  /realtime/{job_id}/video    녹화 영상 스트리밍 (다시보기)
    GET  /realtime/compare/{job_id}  실시간 ↔ 실전연습 결과 비교
"""
from __future__ import annotations

import copy
import json
import os
import random
import subprocess
import sys
import uuid
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel
from typing import Optional

from auth import (
    init_users_db, get_user, verify_password, create_token, decode_token,
    list_users, create_user, delete_user,
)

_BACKEND_DIR    = Path(__file__).parent
_LANG_DIR       = _BACKEND_DIR.parent / "verbal_module"
_NONVERBAL_DIR  = _BACKEND_DIR.parent / "nonverbal_module"
_EVAL_MODEL_DIR = _BACKEND_DIR.parent / "eval_model"

# _BACKEND_DIR 을 맨 앞에 두어 backend/main.py 가 언어모듈/main.py 보다 먼저 찾히게 함
# _LANG_DIR 은 append — insert(0) 하면 uvicorn 리로더 subprocess가
# 언어모듈/main.py 를 먼저 잡아 "app not found" 오류 발생
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_LANG_DIR) not in sys.path:
    sys.path.append(str(_LANG_DIR))
if str(_NONVERBAL_DIR) not in sys.path:
    sys.path.append(str(_NONVERBAL_DIR))
if str(_EVAL_MODEL_DIR) not in sys.path:
    sys.path.append(str(_EVAL_MODEL_DIR))

# .env(OPENAI_API_KEY 등)를 서버 기동 시점에 로드 — 분석 플로우뿐 아니라
# 개선 레퍼런스 이미지 엔드포인트에서도 키가 필요하다.
try:
    from dotenv import load_dotenv
    load_dotenv(str(_LANG_DIR / ".env"))
except ImportError:
    pass

from scorer import calc_scores, aggregate_scores
from deep_report import generate_deep_report
from corrected_frame import get_corrected_reference, CHANGES as CORRECTION_GROUPS
from questions import QUESTION_CATEGORIES, SESSION_QUESTION_COUNT
import preprocessor

# ── 앱 설정 ───────────────────────────────────────────────────────────────────
app = FastAPI(title="PreView API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DIR = Path(__file__).parent / "jobs"
JOBS_DIR.mkdir(exist_ok=True)


@app.on_event("startup")
def _startup():
    init_users_db()

DB_PATH        = Path(__file__).parent / "results_db.json"
_db_lock       = threading.Lock()
_analysis_lock = threading.Lock()
_realtime_lock = threading.Lock()


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────

def _load_db() -> list:
    if DB_PATH.exists():
        with open(DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_db(data: list):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _upsert(entry: dict):
    with _db_lock:
        db = _load_db()
        for i, item in enumerate(db):
            if item["job_id"] == entry["job_id"]:
                # username은 최초 설정 후 백그라운드 업데이트 시에도 유지
                if "username" not in entry and "username" in item:
                    entry["username"] = item["username"]
                db[i] = entry
                _save_db(db)
                return
        db.append(entry)
        _save_db(db)


def _get_current_user(authorization: Optional[str]) -> Optional[dict]:
    """Authorization: Bearer <token> 헤더에서 유저 정보를 추출합니다."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization[7:])
    return payload  # {"sub": username, "role": role} or None


# ── 실시간 모의면접 메타 헬퍼 ──────────────────────────────────────────────────

def _load_realtime_meta(job_dir: Path) -> dict:
    with open(job_dir / "realtime_meta.json", encoding="utf-8") as f:
        return json.load(f)


def _save_realtime_meta(job_dir: Path, meta: dict):
    with open(job_dir / "realtime_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ── 타임스탬프 보정 ──────────────────────────────────────────────────────────

def _shift_timestamps(lang_result: dict, offset: float) -> dict:
    """답변 구간 분석 결과의 타임스탬프를 절대 시각으로 보정합니다."""
    result  = copy.deepcopy(lang_result)
    metrics = result.get("metrics", {})

    for key in ("filler_word", "stuttering"):
        for occ in metrics.get(key, {}).get("occurrences", []):
            if occ.get("time") is not None:
                occ["time"] = round(occ["time"] + offset, 2)

    for occ in metrics.get("long_pauses", {}).get("occurrences", []):
        for field in ("start", "end"):
            if occ.get(field) is not None:
                occ[field] = round(occ[field] + offset, 2)

    return result


# ── 결과 통합 ────────────────────────────────────────────────────────────────

def _aggregate(seg_results: list) -> dict:
    """여러 답변 구간의 언어 분석 결과를 하나로 통합합니다."""
    valid = [r for r in seg_results
             if r.get("language_analysis", {}).get("status") == "success"]
    if not valid:
        return {}
    if len(valid) == 1:
        return valid[0]["language_analysis"]

    all_fillers, all_stutters, all_pauses = [], [], []
    spm_list, rms_list, cv_list, transcripts = [], [], [], []
    total_dur = pure_dur = 0.0

    for seg in valid:
        m   = seg["language_analysis"].get("metrics", {})
        raw = seg["language_analysis"].get("raw_data", {})

        all_fillers .extend(m.get("filler_word", {}).get("occurrences", []))
        all_stutters.extend(m.get("stuttering",  {}).get("occurrences", []))
        all_pauses  .extend(m.get("long_pauses", {}).get("occurrences", []))

        spm = m.get("speech_rate", {}).get("spm", 0)
        if spm > 0:
            spm_list.append(spm)
        vol = m.get("volume_stability", {})
        rms = vol.get("rms_mean", 0)
        if rms > 0:
            rms_list.append(rms)
        cv = vol.get("cv", 0)
        if cv > 0:
            cv_list.append(cv)
        if raw.get("transcript"):
            transcripts.append(raw["transcript"])
        total_dur += raw.get("total_duration_sec",   0)
        pure_dur  += raw.get("pure_speech_time_sec", 0)

    avg_spm    = sum(spm_list) / len(spm_list) if spm_list else 0
    rate_label = "적절" if 270 <= avg_spm <= 350 else ("빠름" if avg_spm > 350 else "느림")
    avg_rms    = sum(rms_list) / len(rms_list) if rms_list else 0
    avg_cv     = sum(cv_list)  / len(cv_list)  if cv_list  else 0.0
    is_loud    = avg_rms >= 0.015

    return {
        "status": "success",
        "error_message": "",
        "raw_data": {
            "transcript":           "\n\n---\n\n".join(transcripts),
            "total_duration_sec":   round(total_dur, 2),
            "pure_speech_time_sec": round(pure_dur,  2),
        },
        "metrics": {
            "filler_word": {
                "count": len(all_fillers),
                "occurrences": sorted(all_fillers,  key=lambda x: x.get("time",  0) or 0),
            },
            "stuttering": {
                "count": len(all_stutters),
                "occurrences": sorted(all_stutters, key=lambda x: x.get("time",  0) or 0),
            },
            "long_pauses": {
                "count": len(all_pauses),
                "occurrences": sorted(all_pauses,   key=lambda x: x.get("start", 0) or 0),
            },
            "speech_rate": {"spm": round(avg_spm, 1), "label": rate_label},
            "volume_stability": {
                "rms_mean":       round(avg_rms, 5),
                "rms_std":        0.0,
                "cv":             round(avg_cv,  4),
                "label":          "안정적" if is_loud else "너무 작음",
                "is_stable":      avg_cv < 0.85,
                "is_loud_enough": is_loud,
            },
        },
    }


# ── ML 평가모델(eval_model) 점수 계산 ────────────────────────────────────────

# 채점표 7개 항목 → 프론트엔드 7-key 스코어 스키마 매핑 (1:1, 병합 없음).
# 표정은 eval_model에 항목이 하나뿐이라 "표정안정성" 하나로만 노출한다.
def _ml_pred_to_scores(ml_pred: dict) -> dict:
    items = ml_pred["items"]
    return {
        "발화속도":     items["말속도"]["score_0to100"],
        "음성명확성":   items["명확성"]["score_0to100"],
        "유창성침묵":   items["침묵"]["score_0to100"],
        "습관어":       items["습관어"]["score_0to100"],
        "시선처리":     items["시선비율"]["score_0to100"],
        "표정안정성":   items["표정"]["score_0to100"],
        "자세안정성":   items["상반신자세"]["score_0to100"],
        "총점":         ml_pred["총점"],
    }


def _compute_ml_scores(agg_lang: dict, nonverbal_result: dict) -> Optional[dict]:
    """
    eval_model(36개 모의면접 영상으로 학습한 RandomForest)로 총점/항목 점수를 예측합니다.
    비전 raw feature나 학습된 모델 파일이 없으면 None을 반환 — 호출부는 이 경우
    scorer.py의 휴리스틱 규칙 기반 점수를 그대로 씁니다(fallback).
    """
    try:
        raw_vision = (nonverbal_result or {}).get("raw_features") or {}
        if not raw_vision:
            return None

        from inference import is_ready, predict_scores
        from feature_adapter import combine

        if not is_ready():
            print("[ML Scoring] eval_model/models/ 없음 — train_final_model.py 먼저 실행 필요")
            return None

        features = combine(raw_vision, agg_lang)
        ml_pred = predict_scores(features)
        ml_pred["scores"] = _ml_pred_to_scores(ml_pred)
        return ml_pred
    except Exception as e:
        print(f"[ML Scoring] 실패, 휴리스틱 점수 사용: {e}")
        return None


# ── STT 교정 (표시 전용) ─────────────────────────────────────────────────────

def _correct_transcript(text: str) -> str:
    """STT 오인식을 GPT-4o-mini로 교정합니다. 분석 데이터에는 영향 없음."""
    if not text or not text.strip():
        return text
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "한국어 면접 답변의 STT(음성인식) 결과를 교정하는 역할입니다. "
                        "발음이 비슷해 잘못 인식된 단어를 문맥에 맞게 올바른 단어로 교정하세요. "
                        "예: '저우' → '저의', '이써요' → '있어요' 등. "
                        "내용·의미·어투는 절대 변경하지 말고 오인식된 단어만 수정하세요. "
                        "교정된 텍스트만 출력하고 설명은 하지 마세요."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Transcript correction] 실패, 원문 사용: {e}")
        return text


# ── 분석 실행 (백그라운드) ────────────────────────────────────────────────────

def _run_analysis(job_id: str, video_path: Path, filename: str):
    # lang_api._init() 호출 전에 .env 로드 — HF_TOKEN/OPENAI_API_KEY 선확보
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_LANG_DIR / ".env"))
    except ImportError:
        pass

    with _analysis_lock:
        job_dir      = JOBS_DIR / job_id
        audio_path   = job_dir / "audio.wav"
        frames_dir   = job_dir / "frames"
        segments_dir = job_dir / "segments"
        segments_dir.mkdir(exist_ok=True)

        frames_count          = 0
        seg_results           = []
        agg_lang              = {}
        nonverbal_result      = {}
        overall_scores        = {}
        ml_pred               = None
        corrected_transcript  = ""
        status                = "failed"
        error                 = ""

        try:
            import importlib.util
            import api as lang_api
            from qa_splitter import find_answer_segments
            from questions   import FIXED_QUESTIONS

            # nonverbal_module api — verbal_module api와 이름 충돌 방지를 위해 파일 직접 로드
            _nv_api_path = str(_NONVERBAL_DIR / "api.py")
            _nv_spec = importlib.util.spec_from_file_location("nonverbal_api", _nv_api_path)
            nonverbal_api = importlib.util.module_from_spec(_nv_spec)
            nonverbal_api.__file__ = _nv_api_path
            _nv_spec.loader.exec_module(nonverbal_api)

            # ─── 1. 오디오 추출 ───────────────────────────────────────────
            preprocessor.extract_audio(str(video_path), str(audio_path))

            # ─── 2. 프레임 추출 (비언어모듈용, 1fps) ─────────────────────
            try:
                frames_info = preprocessor.extract_frames(
                    str(video_path), str(frames_dir), fps=1.0
                )
                preprocessor.save_frames_metadata(
                    frames_info, str(job_dir / "frames_metadata.json")
                )
                frames_count = len(frames_info)
                print(f"[Frames] {frames_count}장 추출 완료")
            except Exception as e:
                print(f"[Frames] 프레임 추출 실패: {e}")

            # ─── 3. 전체 오디오 STT ──────────────────────────────────────
            print("[STT] 전체 오디오 전사 시작...")
            full_text, words_info, segments_info = lang_api.transcribe_file(str(audio_path))
            print(f"[STT] 완료 — 세그먼트 {len(segments_info)}개, 단어 {len(words_info)}개")

            # ─── 4. GPT Q&A 분리 ─────────────────────────────────────────
            print("[QA] 질문/답변 분리 시작...")
            answer_segs = find_answer_segments(segments_info, FIXED_QUESTIONS)

            if not answer_segs:
                # fallback: 전체를 하나의 답변으로
                print("[QA] 분리 실패, 전체를 하나의 답변으로 처리")
                last_end = segments_info[-1]["end"] if segments_info else None
                answer_segs = [{
                    "index": 0, "question": "", "question_start": 0.0,
                    "start": 0.0, "end": last_end,
                }]

            print(f"[Pipeline] 답변 수: {len(answer_segs)}")

            # ─── 5. 비언어 분석 (영상에서 직접 샘플링) ────────────────────
            # frames_dir(1fps 썸네일용 JPEG)와 별개로, 영상 파일을 직접 읽어
            # eval_model 학습 때와 동일한 코드(vision_features.py)로 시선/표정/자세를 분석한다.
            print("[Vision] 비전 분석 시작...")
            try:
                nonverbal_result = nonverbal_api.analyze_nonverbal(str(video_path))
                print(f"[Vision] 완료 — status: {nonverbal_result.get('status')}")
                if nonverbal_result.get("errors"):
                    print(f"[Vision] 부분 오류: {nonverbal_result['errors']}")
            except Exception as e:
                print(f"[Vision] 분석 실패: {e}")

            # ─── 6. 답변별 언어 분석 ─────────────────────────────────────
            for seg in answer_segs:
                answer_segment = {"start": seg["start"], "end": seg["end"]}
                lang_result    = lang_api.analyze_from_words(
                    words_info, str(audio_path), answer_segment
                )
                seg_results.append({
                    "index":             seg["index"],
                    "question":          seg.get("question", ""),
                    "question_start":    seg.get("question_start"),
                    "start":             seg["start"],
                    "end":               seg.get("end"),
                    "language_analysis": lang_result,
                    "scores":            calc_scores(lang_result),
                })

            # ─── 7. 집계 ─────────────────────────────────────────────────
            agg_lang = _aggregate(seg_results)
            if not agg_lang:
                raise RuntimeError("모든 답변 구간 분석에 실패했습니다")

            # 비언어 점수를 반영한 최종 점수 계산
            nv = nonverbal_result if nonverbal_result.get("status") != "failed" else None
            overall_scores = aggregate_scores(
                [s["scores"] for s in seg_results],
                nonverbal_analysis=nv,
            )

            # ─── 7.5. eval_model(ML) 점수 — 되면 휴리스틱 점수를 대체 ──────
            ml_pred = _compute_ml_scores(agg_lang, nonverbal_result)
            if ml_pred:
                print(f"[ML Scoring] 성공 — 총점 {ml_pred['총점']}")
                overall_scores = ml_pred["scores"]

            # ─── 8. 표시용 텍스트 교정 (분석 데이터와 분리) ──────────────
            raw_transcript = agg_lang.get("raw_data", {}).get("transcript", "")
            if raw_transcript:
                print("[Transcript] GPT 교정 중...")
                corrected_transcript = _correct_transcript(raw_transcript)
                print("[Transcript] 교정 완료")

            status = "completed"

        except Exception as e:
            import traceback
            error = str(e)
            print(f"[Analysis] 오류: {error}")
            traceback.print_exc()

    _upsert({
        "job_id":               job_id,
        "timestamp":            datetime.now().isoformat(),
        "filename":             filename,
        "status":               status,
        "error":                error,
        "language_analysis":    agg_lang,
        "nonverbal_analysis":   nonverbal_result,
        "ml_scores":            ml_pred,
        "corrected_transcript": corrected_transcript,
        "answers":              seg_results,
        "scores":               overall_scores,
        "frames_count":         frames_count,
    })


# ── 실시간 모의면접 분석 실행 (백그라운드) ────────────────────────────────────

def _run_realtime_analysis(job_id: str):
    """
    하나로 이어진 전체 녹화본을 한 번에 분석하고, 클라이언트가 보낸
    timestamps(질문별 {index, question, start, end})로 답변 구간을 나눕니다.
    클립을 병합할 필요가 없으므로 /analyze(단일 영상) 플로우와 동일한 구조입니다.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_LANG_DIR / ".env"))
    except ImportError:
        pass

    with _analysis_lock:
        job_dir    = JOBS_DIR / job_id
        frames_dir = job_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        filename              = "실시간 모의면접"
        category              = ""
        videotype             = "realtime"
        frames_count          = 0
        seg_results           = []
        agg_lang              = {}
        nonverbal_result      = {}
        overall_scores        = {}
        ml_pred               = None
        corrected_transcript  = ""
        status                = "failed"
        error                 = ""

        try:
            import importlib.util
            import api as lang_api

            meta       = _load_realtime_meta(job_dir)
            category   = meta["category"]
            videotype  = meta.get("mode", "realtime")
            filename   = f"{meta['category']} 실시간 모의면접"
            video_path = job_dir / meta["video_filename"]
            audio_path = job_dir / "audio.wav"

            # nonverbal_module api — verbal_module api와 이름 충돌 방지를 위해 파일 직접 로드
            _nv_api_path = str(_NONVERBAL_DIR / "api.py")
            _nv_spec = importlib.util.spec_from_file_location("nonverbal_api", _nv_api_path)
            nonverbal_api = importlib.util.module_from_spec(_nv_spec)
            nonverbal_api.__file__ = _nv_api_path
            _nv_spec.loader.exec_module(nonverbal_api)

            # ─── 1. 오디오 추출 ───────────────────────────────────────────
            preprocessor.extract_audio(str(video_path), str(audio_path))

            # ─── 2. 프레임 추출 (비언어모듈용, 1fps, 영상 전체) ──────────
            try:
                frames_info = preprocessor.extract_frames(
                    str(video_path), str(frames_dir), fps=1.0
                )
                preprocessor.save_frames_metadata(
                    frames_info, str(job_dir / "frames_metadata.json")
                )
                frames_count = len(frames_info)
                print(f"[Frames] {frames_count}장 추출 완료")
            except Exception as e:
                print(f"[Frames] 프레임 추출 실패: {e}")

            # ─── 3. 전체 오디오 STT (1회) ─────────────────────────────────
            print("[STT] 전체 오디오 전사 시작...")
            full_text, words_info, segments_info = lang_api.transcribe_file(str(audio_path))
            print(f"[STT] 완료 — 단어 {len(words_info)}개")

            # ─── 4. 비언어 분석 (영상에서 직접 샘플링) ────────────────────
            print("[Vision] 비전 분석 시작...")
            try:
                nonverbal_result = nonverbal_api.analyze_nonverbal(str(video_path))
                print(f"[Vision] 완료 — status: {nonverbal_result.get('status')}")
            except Exception as e:
                print(f"[Vision] 분석 실패: {e}")

            # ─── 5. 질문별(타임스탬프 구간) 언어 분석 ────────────────────
            for ts in sorted(meta["timestamps"], key=lambda t: t["index"]):
                answer_segment = {"start": ts["start"], "end": ts["end"]}
                lang_result    = lang_api.analyze_from_words(
                    words_info, str(audio_path), answer_segment
                )
                seg_results.append({
                    "index":             ts["index"],
                    "question":          ts["question"],
                    "question_start":    ts["start"],
                    "start":             ts["start"],
                    "end":               ts["end"],
                    "language_analysis": lang_result,
                    "scores":            calc_scores(lang_result),
                })

            # ─── 6. 집계 ─────────────────────────────────────────────────
            agg_lang = _aggregate(seg_results)
            if not agg_lang:
                raise RuntimeError("모든 답변 구간 분석에 실패했습니다")

            nv = nonverbal_result if nonverbal_result.get("status") != "failed" else None
            overall_scores = aggregate_scores(
                [s["scores"] for s in seg_results],
                nonverbal_analysis=nv,
            )

            # ─── 6.5. eval_model(ML) 점수 — 되면 휴리스틱 점수를 대체 ──────
            ml_pred = _compute_ml_scores(agg_lang, nonverbal_result)
            if ml_pred:
                print(f"[ML Scoring] 성공 — 총점 {ml_pred['총점']}")
                overall_scores = ml_pred["scores"]

            raw_transcript = agg_lang.get("raw_data", {}).get("transcript", "")
            if raw_transcript:
                print("[Transcript] GPT 교정 중...")
                corrected_transcript = _correct_transcript(raw_transcript)
                print("[Transcript] 교정 완료")

            status = "completed"

        except Exception as e:
            import traceback
            error = str(e)
            print(f"[Realtime Analysis] 오류: {error}")
            traceback.print_exc()

    _upsert({
        "job_id":               job_id,
        "timestamp":            datetime.now().isoformat(),
        "filename":             filename,
        "status":               status,
        "error":                error,
        "category":             category,
        "videotype":            videotype,
        "language_analysis":    agg_lang,
        "nonverbal_analysis":   nonverbal_result,
        "ml_scores":            ml_pred,
        "corrected_transcript": corrected_transcript,
        "answers":              seg_results,
        "scores":               overall_scores,
        "frames_count":         frames_count,
    })


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@app.post("/analyze")
async def upload_and_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    """영상 업로드 및 분석 시작"""
    user   = _get_current_user(authorization)
    job_id   = str(uuid.uuid4())
    job_dir  = JOBS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    suffix     = Path(file.filename).suffix or ".mp4"
    video_path = job_dir / f"original{suffix}"

    content = await file.read()
    with open(video_path, "wb") as f:
        f.write(content)

    _upsert({
        "job_id": job_id, "timestamp": datetime.now().isoformat(),
        "filename": file.filename, "status": "processing",
        "error": "", "speaker_count": 0,
        "language_analysis": {}, "answers": [], "scores": {}, "frames_count": 0,
        "username": user["sub"] if user else "admin",
    })

    background_tasks.add_task(_run_analysis, job_id, video_path, file.filename)
    return {"job_id": job_id, "status": "processing"}


# ── 실시간 모의면접 엔드포인트 ─────────────────────────────────────────────────

class RealtimeStartRequest(BaseModel):
    category: str
    mode: str = "realtime"


@app.get("/realtime/questions")
def get_realtime_questions():
    """분야별 실시간 면접 질문 목록"""
    return QUESTION_CATEGORIES


@app.post("/realtime/start")
def start_realtime_interview(body: RealtimeStartRequest):
    """
    실시간 면접 세션 시작 — job_id 발급, 분야 질문 풀에서 SESSION_QUESTION_COUNT개를
    무작위로 뽑아(순서도 함께 섞임) 반환. mode(realtime/practice)와 무관하게 동일하게 적용.
    """
    pool = QUESTION_CATEGORIES.get(body.category)
    if not pool:
        raise HTTPException(400, "알 수 없는 분야입니다")

    n = min(SESSION_QUESTION_COUNT, len(pool))
    questions = random.sample(pool, n)

    job_id  = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    with _realtime_lock:
        _save_realtime_meta(job_dir, {
            "category": body.category, "mode": body.mode, "questions": questions,
        })

    return {"job_id": job_id, "questions": questions}


@app.post("/realtime/{job_id}/finish")
async def finish_realtime_interview(
    job_id:           str,
    background_tasks: BackgroundTasks,
    file:             UploadFile = File(...),
    timestamps:       str        = Form(...),
    authorization:    Optional[str] = Header(default=None),
):
    """연속 녹화된 영상 1개 + 질문별 타임스탬프 배열을 업로드 받아 분석을 시작합니다."""
    job_dir   = JOBS_DIR / job_id
    meta_path = job_dir / "realtime_meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Job not found")

    try:
        ts_list = json.loads(timestamps)
    except json.JSONDecodeError:
        raise HTTPException(400, "타임스탬프 형식이 올바르지 않습니다")
    if not ts_list:
        raise HTTPException(400, "타임스탬프 데이터가 없습니다")

    video_filename = "video.webm"
    content = await file.read()
    with open(job_dir / video_filename, "wb") as f:
        f.write(content)

    with _realtime_lock:
        meta = _load_realtime_meta(job_dir)
        meta["video_filename"] = video_filename
        meta["timestamps"]     = ts_list
        _save_realtime_meta(job_dir, meta)

    rt_user = _get_current_user(authorization)
    _upsert({
        "job_id": job_id, "timestamp": datetime.now().isoformat(),
        "filename": f"{meta['category']} 실시간 모의면접", "status": "processing",
        "category": meta["category"], "videotype": meta.get("mode", "realtime"),
        "error": "", "language_analysis": {}, "answers": [], "scores": {}, "frames_count": 0,
        "username": rt_user["sub"] if rt_user else "admin",
    })

    background_tasks.add_task(_run_realtime_analysis, job_id)
    return {"job_id": job_id, "status": "processing"}


@app.get("/realtime/{job_id}/video")
def serve_realtime_video(job_id: str):
    """녹화된 실시간/실전연습 영상을 그대로 스트리밍합니다 (다시보기용)."""
    job_dir   = JOBS_DIR / job_id
    meta_path = job_dir / "realtime_meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Job not found")

    meta       = _load_realtime_meta(job_dir)
    video_path = job_dir / meta.get("video_filename", "video.webm")
    if not video_path.exists():
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")

    return FileResponse(str(video_path), media_type="video/webm")


@app.get("/realtime/compare/{job_id}")
def compare_realtime_results(
    job_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """
    실시간 모의면접 결과를 같은 분야의 반대 모드(실전연습 ↔ 일반) 중
    가장 최근 완료된 결과와 비교합니다. 본인 기록 안에서만 매칭합니다.
    """
    user    = _get_current_user(authorization)
    db      = _load_db()
    current = next((e for e in db if e["job_id"] == job_id), None)
    if current is None or current.get("status") != "completed":
        raise HTTPException(404, "Job not found or not completed")

    category   = current.get("category")
    other_mode = "realtime" if current.get("videotype") == "practice" else "practice"
    owner      = current.get("username")
    candidates = [
        e for e in db
        if e.get("status") == "completed"
        and e.get("category") == category
        and e.get("videotype") == other_mode
        and e["job_id"] != job_id
        and (user and user.get("role") == "admin" or e.get("username") == owner)
    ]
    previous = max(candidates, key=lambda e: e["timestamp"], default=None)

    diff: dict = {}
    if previous:
        cs, ps = current.get("scores", {}), previous.get("scores", {})
        for k in cs:
            if k == "총점":
                continue
            c, p = cs.get(k), ps.get(k)
            if c is not None and p is not None:
                diff[k] = round(c - p, 1)

    return {"current": current, "previous": previous, "diff": diff}


@app.get("/results/{job_id}")
def get_results(job_id: str):
    """분석 결과 조회"""
    db = _load_db()
    for e in db:
        if e["job_id"] == job_id:
            return e
    raise HTTPException(404, "Job not found")


_deep_report_locks: dict[str, threading.Lock] = {}
_deep_report_locks_guard = threading.Lock()


@app.get("/deep-report/{job_id}")
def get_deep_report(job_id: str):
    """
    음성·비전 특징 전용 심층 리포트. 결과 화면에서 필요할 때 생성하며 GPT 호출 2회라
    처리에 1~2분 걸릴 수 있습니다. 같은 스키마 버전으로 한 번 생성된 결과는 해당
    job에 캐시되어 재호출 시 즉시 반환됩니다.
    """
    db = _load_db()
    job = next((e for e in db if e["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "completed":
        raise HTTPException(409, "분석이 아직 완료되지 않았습니다")

    if (job.get("deep_report") or {}).get("report_version") == 4:
        return job["deep_report"]

    with _deep_report_locks_guard:
        lock = _deep_report_locks.setdefault(job_id, threading.Lock())

    with lock:
        # 락 대기 중 다른 요청이 먼저 만들어놨을 수 있으니 다시 확인
        db = _load_db()
        job = next((e for e in db if e["job_id"] == job_id), None)
        if (job.get("deep_report") or {}).get("report_version") == 4:
            return job["deep_report"]

        report = generate_deep_report(job)
        if report is None:
            raise HTTPException(503, "심층 리포트를 생성할 수 없습니다 (API 키/생성 실패)")

        job["deep_report"] = report
        _upsert(job)
        return report


@app.get("/history")
def get_history(authorization: Optional[str] = Header(default=None)):
    """완료된 분석 기록 (최신순). admin은 전체, 일반 유저는 본인 것만."""
    user = _get_current_user(authorization)
    db   = _load_db()
    completed = [e for e in db if e.get("status") == "completed"]
    if user and user.get("role") == "admin":
        filtered = completed                                    # admin: 전체
    elif user:
        filtered = [e for e in completed
                    if e.get("username") == user["sub"]]       # user: 본인만
    else:
        filtered = []                                           # 미인증: 빈 목록
    return sorted(filtered, key=lambda x: x["timestamp"], reverse=True)


@app.get("/compare/{job_id}")
def compare_results(job_id: str, authorization: Optional[str] = Header(default=None)):
    """현재 업로드 분석을 같은 사용자의 가장 최근 이전 분석과 비교한다."""
    user = _get_current_user(authorization)
    db = _load_db()
    current = next(
        (entry for entry in db if entry.get("job_id") == job_id and entry.get("status") == "completed"),
        None,
    )
    if current is None:
        raise HTTPException(404, "Job not found or not completed")

    is_admin = bool(user and user.get("role") == "admin")
    if not is_admin and (not user or current.get("username") != user.get("sub")):
        raise HTTPException(403, "본인의 분석 기록만 비교할 수 있습니다")

    owner = current.get("username")
    candidates = [
        entry for entry in db
        if entry.get("status") == "completed"
        and entry.get("job_id") != job_id
        and entry.get("username") == owner
        and entry.get("timestamp", "") < current.get("timestamp", "")
        and not entry.get("videotype")
    ]
    previous = max(candidates, key=lambda entry: entry.get("timestamp", ""), default=None)

    diff: dict = {}
    if previous:
        cs, ps = current.get("scores", {}), previous.get("scores", {})
        for k in cs:
            if k == "총점":
                continue
            c, p = cs.get(k), ps.get(k)
            if c is not None and p is not None:
                diff[k] = round(c - p, 1)

    return {"current": current, "previous": previous, "diff": diff}


@app.get("/audio-clip/{job_id}")
def serve_audio_clip(
    job_id:  str,
    start:   float,
    end:     float,
    context: float = 0.5,
):
    """
    감점 구간의 오디오 클립을 WAV로 반환합니다.
    context: 앞뒤로 추가할 여유 시간(초). 기본 0.5초.
    """
    audio_path = JOBS_DIR / job_id / "audio.wav"
    if not audio_path.exists():
        raise HTTPException(404, "오디오 파일을 찾을 수 없습니다")

    clip = preprocessor.get_audio_clip_bytes(str(audio_path), start, end, context)
    return Response(
        content=clip,
        media_type="audio/wav",
        headers={
            "Cache-Control": "max-age=3600",
            "Content-Length": str(len(clip)),
            "Accept-Ranges": "bytes",
        },
    )


def _resolve_video_path(job_id: str) -> Path:
    """업로드(/analyze)/실시간(/realtime) 두 플로우 모두에서 원본 영상 파일 경로를 찾습니다."""
    job_dir = JOBS_DIR / job_id
    # job_id가 ".." 같은 값이면 jobs/ 밖의 디렉터리를 가리킬 수 있으므로 차단
    if job_dir.resolve().parent != JOBS_DIR.resolve():
        raise HTTPException(404, "Job not found")
    meta_path = job_dir / "realtime_meta.json"
    if meta_path.exists():
        meta = _load_realtime_meta(job_dir)
        return job_dir / meta.get("video_filename", "video.webm")

    matches = sorted(job_dir.glob("original.*"))
    if matches:
        return matches[0]
    raise HTTPException(404, "영상 파일을 찾을 수 없습니다")


def _extract_frame_jpeg(video_path: Path, t: float) -> bytes:
    """영상의 t초 지점 프레임 하나를 JPEG bytes로 추출합니다."""
    proc = subprocess.run(
        ["ffmpeg", "-ss", f"{max(0.0, t):.3f}", "-i", str(video_path),
         "-frames:v", "1", "-q:v", "3", "-f", "image2", "-vcodec", "mjpeg", "pipe:1"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise HTTPException(500, f"프레임 추출 실패: {proc.stderr.decode(errors='ignore')[:300]}")
    return proc.stdout


@app.get("/frame/{job_id}")
def serve_frame(job_id: str, t: float = 0.0):
    """
    지정 시각(t초)의 영상 프레임 하나를 JPEG로 반환합니다.
    비전 분석(표정/시선/자세) 타임라인 구간을 클릭했을 때 실제 장면을 보여주는 용도.
    """
    video_path = _resolve_video_path(job_id)
    if not video_path.exists():
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")

    return Response(
        content=_extract_frame_jpeg(video_path, t),
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


def _representative_problem_times(job: dict, group: str) -> list[float]:
    """각 비전 항목의 대표 장면을 최대 두 개 고른다.

    자세 문제가 감지되지 않은 기록은 버튼을 숨기지 않고, 답변 구간의 1/3과
    2/3 지점을 안정적인 자세의 대표 장면으로 사용한다.
    """
    nv = job.get("nonverbal_analysis", {}) or {}
    if group in ("gaze", "expression"):
        key = "gaze_deductions" if group == "gaze" else "expression_deductions"
        segments = sorted(
            nv.get(key, []) or [],
            key=lambda item: float(item.get("end", 0)) - float(item.get("start", 0)),
            reverse=True,
        )
        candidates = [
            (float(item.get("start", 0)) + float(item.get("end", item.get("start", 0)))) / 2
            for item in segments
        ]
    else:
        points = sorted(
            nv.get("posture_deductions", []) or [],
            key=lambda item: float(item.get("confidence", 0)),
            reverse=True,
        )
        candidates = [float(item.get("sec", 0)) for item in points]
        if not candidates:
            duration = max(
                (float(answer.get("end", 0) or 0) for answer in (job.get("answers", []) or [])),
                default=0.0,
            )
            if duration > 0:
                candidates = [duration / 3, duration * 2 / 3]

    selected: list[float] = []
    for candidate in candidates:
        # 연속 샘플로 사실상 같은 화면이 두 번 선택되는 것을 막는다.
        if all(abs(candidate - existing) >= 1.5 for existing in selected):
            selected.append(round(max(0.0, candidate), 2))
        if len(selected) == 2:
            break
    return selected


@app.get("/improvement-reference/{job_id}/{group}")
def serve_improvement_reference(job_id: str, group: str):
    """대표 문제 장면 두 개를 참고해 만든 항목별 개선 레퍼런스 이미지 한 장을 반환한다."""
    if group not in CORRECTION_GROUPS:
        raise HTTPException(404, f"알 수 없는 group: {group}")

    db = _load_db()
    job = next((entry for entry in db if entry.get("job_id") == job_id), None)
    if job is None:
        raise HTTPException(404, "Job not found")

    times = _representative_problem_times(job, group)
    if not times:
        raise HTTPException(404, "해당 항목의 문제 구간이 없습니다")

    video_path = _resolve_video_path(job_id)
    if not video_path.exists():
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")

    path = get_corrected_reference(
        JOBS_DIR / job_id,
        group,
        times,
        get_frames=lambda: [_extract_frame_jpeg(video_path, time) for time in times],
    )
    if path is None or not path.exists():
        raise HTTPException(503, "개선 레퍼런스 이미지를 생성할 수 없습니다")

    return FileResponse(
        str(path),
        media_type="image/png",
        headers={
            "Cache-Control": "max-age=86400",
            "X-Problem-Times": ",".join(str(time) for time in times),
        },
    )


# ── 인증 엔드포인트 ───────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def login(body: LoginRequest):
    """로그인 → JWT 토큰 반환"""
    user = get_user(body.username)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
    token = create_token(user["username"], user["role"])
    return {"access_token": token, "token_type": "bearer",
            "username": user["username"], "role": user["role"]}


# ── 관리자 엔드포인트 ─────────────────────────────────────────────────────────

def _require_admin(authorization: Optional[str]) -> dict:
    """admin 권한을 확인하고 payload를 반환합니다. 실패 시 HTTPException."""
    user = _get_current_user(authorization)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    return user


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


@app.get("/admin/users")
def admin_list_users(authorization: Optional[str] = Header(default=None)):
    """유저 목록 조회 (admin 전용)"""
    _require_admin(authorization)
    return list_users()


@app.post("/admin/users", status_code=201)
def admin_create_user(
    body: CreateUserRequest,
    authorization: Optional[str] = Header(default=None),
):
    """유저 추가 (admin 전용)"""
    _require_admin(authorization)
    ok = create_user(body.username, body.password, body.role)
    if not ok:
        raise HTTPException(status_code=409, detail="이미 존재하는 아이디입니다")
    return {"message": f"유저 '{body.username}' 생성 완료"}


@app.delete("/admin/users/{username}")
def admin_delete_user(
    username: str,
    authorization: Optional[str] = Header(default=None),
):
    """유저 삭제 (admin 전용, admin 계정 자신은 삭제 불가)"""
    _require_admin(authorization)
    ok = delete_user(username)
    if not ok:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없거나 삭제할 수 없습니다")
    return {"message": f"유저 '{username}' 삭제 완료"}
