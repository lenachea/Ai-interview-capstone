"""
main.py
-------
FastAPI 서버: 영상 → 오디오+프레임 분리 → 화자 분리 → 답변별 언어분석 → 점수 계산

실행:
    cd backend
    uvicorn main:app --reload --port 8000

엔드포인트:
    POST /analyze            영상 업로드 + 분석 시작
    GET  /results/{job_id}   분석 결과 조회
    GET  /history            완료된 분석 기록 목록 (최신순)
    GET  /compare/{job_id}   현재·이전 결과 + 점수 차이
    GET  /audio-clip/{job_id}?start=&end=  감점 구간 오디오 클립
"""
from __future__ import annotations

import copy
import json
import os
import sys
import uuid
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

_BACKEND_DIR = Path(__file__).parent
_LANG_DIR    = _BACKEND_DIR.parent / "verbal_module"

# _BACKEND_DIR 을 맨 앞에 두어 backend/main.py 가 언어모듈/main.py 보다 먼저 찾히게 함
# _LANG_DIR 은 append — insert(0) 하면 uvicorn 리로더 subprocess가
# 언어모듈/main.py 를 먼저 잡아 "app not found" 오류 발생
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_LANG_DIR) not in sys.path:
    sys.path.append(str(_LANG_DIR))

from scorer import calc_scores, aggregate_scores
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

DB_PATH        = Path(__file__).parent / "results_db.json"
_db_lock       = threading.Lock()
_analysis_lock = threading.Lock()


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
                db[i] = entry
                _save_db(db)
                return
        db.append(entry)
        _save_db(db)


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
        overall_scores        = {}
        corrected_transcript  = ""
        status                = "failed"
        error                 = ""

        try:
            import api as lang_api
            from qa_splitter import find_answer_segments
            from questions   import FIXED_QUESTIONS

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

            # ─── 5. 답변별 언어 분석 ─────────────────────────────────────
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

            # ─── 6. 집계 ─────────────────────────────────────────────────
            agg_lang = _aggregate(seg_results)
            if not agg_lang:
                raise RuntimeError("모든 답변 구간 분석에 실패했습니다")

            # 전체 점수: 답변별 점수를 평균 (spm 상쇄 방지)
            overall_scores = aggregate_scores([s["scores"] for s in seg_results])

            # ─── 7. 표시용 텍스트 교정 (분석 데이터와 분리) ──────────────
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
):
    """영상 업로드 및 분석 시작"""
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
    })

    background_tasks.add_task(_run_analysis, job_id, video_path, file.filename)
    return {"job_id": job_id, "status": "processing"}


@app.get("/results/{job_id}")
def get_results(job_id: str):
    """분석 결과 조회"""
    db = _load_db()
    for e in db:
        if e["job_id"] == job_id:
            return e
    raise HTTPException(404, "Job not found")


@app.get("/history")
def get_history():
    """완료된 분석 기록 (최신순)"""
    db = _load_db()
    return sorted([e for e in db if e["status"] == "completed"],
                  key=lambda x: x["timestamp"], reverse=True)


@app.get("/compare/{job_id}")
def compare_results(job_id: str):
    """현재 분석과 직전 분석 비교"""
    db        = _load_db()
    completed = sorted([e for e in db if e["status"] == "completed"],
                       key=lambda x: x["timestamp"])

    current = previous = None
    for i, e in enumerate(completed):
        if e["job_id"] == job_id:
            current  = e
            previous = completed[i - 1] if i > 0 else None
            break

    if current is None:
        raise HTTPException(404, "Job not found or not completed")

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
