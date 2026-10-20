"""
deep_report.py
--------------
음성·비전 실측 특징만 해석하는 면접 태도 심층 리포트 생성기.

다른 파일(기존 점수 산출, 음성/비전 분석)은 전혀 건드리지 않음 — 이미 계산된 결과를
읽어서 해석하는 역할만 한다. 결과 화면이 열릴 때 main.py의 전용 엔드포인트가 호출하고,
한 번 생성된 동일 버전의 리포트는 저장해 재사용한다.

2단계 생성:
  1단계(질문별 심층분석) — answers[] 각 구간의 실측 지표(발화속도/습관어/침묵/
      시선·표정·자세 이탈 횟수)를 교차 집계해 음성/비전 분석을 각각 받는다.
  2단계(종합) — 1단계 결과 + 전체 지표를 입력으로 총평/역량별평가/행동패턴/
      우선순위/훈련계획을 받는다.

답변 전사는 모델에 전달하지 않는다. 질문 문구도 구간 표시용 라벨일 뿐 평가 근거로
사용하지 못하게 명시해 답변 내용·논리·직무 역량 평가가 섞이지 않도록 한다.
"""
from __future__ import annotations

import json
import os
from typing import Optional

MODEL = "gpt-5.6-sol"
REPORT_VERSION = 4

# report_generator.py와 동일한 평가 기준 — 두 리포트가 서로 다른 목표치를
# 말하지 않도록 기준 문구를 그대로 공유한다.
EVAL_CRITERIA = """[이 시스템의 평가 기준]
- 발화 속도: 분당 270~350음절이 적정. 270 미만은 느림, 350 초과는 빠름.
- 정면 응시 비율: 0.8 이상 안정적, 0.6~0.8 가끔 이탈, 0.6 미만 정면 이탈 잦음.
- 자세 점수: 100점 만점, 95 이상 매우 안정적, 85 미만 개선 필요.
- 7개 항목 점수(0~100)는 36개 모의면접 영상을 사람이 채점한 데이터로 학습한
  회귀 모델의 예측값이며, 각 항목의 raw 지표(아래)가 모델이 실제로 본 입력이다."""


# ── 1. 저장된 데이터에서 "교차 집계" 계산 (LLM 호출 없이 순수 계산) ───────────

def _overlap_sec(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _count_in_window(deductions: list, start: float, end: float, key_start="start", key_end=None) -> tuple[int, float]:
    """deductions 중 [start,end] 구간과 겹치는 것의 개수와 총 겹침 시간(초)."""
    count = 0
    total = 0.0
    for d in deductions:
        d_start = d.get(key_start, d.get("sec"))
        d_end = d.get(key_end) if key_end else d.get("end", d_start)
        if d_start is None:
            continue
        if d_end is None:
            d_end = d_start
        ov = _overlap_sec(start, end, d_start, d_end)
        if ov > 0 or (d_start >= start and d_start < end):
            count += 1
            total += ov if ov > 0 else 0.5  # posture_deductions는 점(sec) 단위라 0.5초(샘플 간격)로 근사
    return count, round(total, 2)


def build_cross_modal_data(job: dict) -> dict:
    """answers[] 구간별로 음성·비전 이탈 지표를 교차 집계한다. 전부 이미 저장된 값의 재계산일 뿐,
    새로운 측정은 하지 않는다."""
    nv = job.get("nonverbal_analysis", {}) or {}
    gaze_deds = nv.get("gaze_deductions", []) or []
    expr_deds = nv.get("expression_deductions", []) or []
    posture_deds = nv.get("posture_deductions", []) or []

    per_question = []
    for position, a in enumerate(job.get("answers", [])):
        start, end = a.get("start", 0.0), a.get("end") or start
        lm = (a.get("language_analysis") or {}).get("metrics", {}) or {}
        gaze_n, gaze_sec = _count_in_window(gaze_deds, start, end)
        expr_n, expr_sec = _count_in_window(expr_deds, start, end)
        post_n, post_sec = _count_in_window(posture_deds, start, end, key_start="sec")

        pauses = lm.get("long_pauses", {}).get("occurrences", []) or []
        pause_total = round(sum(float(p.get("duration") or 0.0) for p in pauses), 2)

        per_question.append({
            "index": a.get("index") if a.get("index") is not None else position,
            "question_label": a.get("question", "") or f"질문 {len(per_question) + 1}",
            "start_sec": start,
            "end_sec": end,
            "duration_sec": round(end - start, 1),
            "spm": lm.get("speech_rate", {}).get("spm"),
            "speech_rate_label": lm.get("speech_rate", {}).get("label"),
            "filler_count": lm.get("filler_word", {}).get("count", 0),
            "stutter_count": lm.get("stuttering", {}).get("count", 0),
            "long_pause_count": len(pauses),
            "long_pause_total_sec": pause_total,
            "volume_cv": lm.get("volume_stability", {}).get("cv"),
            "volume_label": lm.get("volume_stability", {}).get("label"),
            "gaze_deviation_count": gaze_n,
            "gaze_deviation_sec": gaze_sec,
            "expression_deviation_count": expr_n,
            "expression_deviation_sec": expr_sec,
            "posture_deviation_count": post_n,
        })

    lang = job.get("language_analysis", {}) or {}
    metrics = lang.get("metrics", {}) or {}
    raw = lang.get("raw_data", {}) or {}
    gaze_summary = nv.get("gaze_summary", {}) or {}
    expr_summary = nv.get("expression_summary", {}) or {}
    posture_summary = nv.get("posture_summary", {}) or {}

    overall = {
        "scores_0to100": job.get("scores", {}),
        "total_duration_sec": raw.get("total_duration_sec"),
        "pure_speech_time_sec": raw.get("pure_speech_time_sec"),
        "spm": metrics.get("speech_rate", {}).get("spm"),
        "filler_total": metrics.get("filler_word", {}).get("count", 0),
        "stutter_total": metrics.get("stuttering", {}).get("count", 0),
        "long_pause_total": metrics.get("long_pauses", {}).get("count", 0),
        "volume_cv": metrics.get("volume_stability", {}).get("cv"),
        "volume_label": metrics.get("volume_stability", {}).get("label"),
        "gaze_center_ratio": gaze_summary.get("gaze_ratio"),
        "gaze_direction_ratios": gaze_summary.get("direction_ratios"),
        "expression_dominant": expr_summary.get("dominant_emotion"),
        "expression_positive_ratio": expr_summary.get("positive_ratio"),
        "expression_negative_ratio": expr_summary.get("negative_ratio"),
        "posture_score_mean": posture_summary.get("score_mean"),
        "posture_score_min": posture_summary.get("score_min"),
        "posture_slouch_count": posture_summary.get("slouch_count"),
        "posture_slouch_ratio": posture_summary.get("slouch_ratio"),
    }

    return {"per_question": per_question, "overall": overall}


# ── 2. 1단계: 질문별 심층 분석 ───────────────────────────────────────────────

_STAGE1_SYSTEM = f"""당신은 지원자의 면접 태도를 코칭하는 전문가입니다.
각 질문 구간에서 실측된 음성·비전 특징만 근거로 전달 태도를 분석하세요.

{EVAL_CRITERIA}

규칙:
- 답변 전사는 제공되지 않습니다. 질문이나 답변의 내용, 논리, 경험, 직무 역량을 평가하지 마세요.
- question_label은 구간 식별용일 뿐 분석 근거로 사용하지 마세요.
- 비전은 시선·표정·자세만, 음성은 속도·침묵·습관어·더듬음·음량만 분석하세요.
- 사용자가 수치를 해석하게 만들지 말고, 먼저 "어떻게 보이고 들리는지"를 쉬운 말로 설명하세요.
- 숫자는 판단을 이해하는 데 꼭 필요한 경우에만 문단당 하나 이하로 짧게 덧붙이세요.
- "기준 85점 대비 평균 88점", "정면 응시 29%"처럼 수치와 기준을 연달아 나열하지 마세요.
- 내부 평가 기준은 판단에만 사용하고, 결과 문장에서는 "대체로 안정적", "자주 흐트러짐"처럼 풀어 쓰세요.
- 관찰된 특징이 전달 인상에 줄 수 있는 영향과 바로 연습할 행동을 자연스럽게 연결하세요.
- 표정/시선만으로 심리 상태, 자신감, 성격, 감정을 단정하지 마세요.
- '데이터를 종합하면', '전반적으로 우수합니다' 같은 상투적인 문장을 반복하지 마세요.
- 각 질문마다 아래 JSON 스키마를 채우고 모든 텍스트는 한국어로 작성하세요.

출력 형식 (questions 배열, 입력된 순서와 개수 그대로):
{{
  "questions": [
    {{
      "index": 0,
      "vision": {{
        "summary": "사용자가 한 번에 이해할 수 있는 비전 특징 분석 2~3문장",
        "strengths": ["쉽게 풀어 쓴 강점"],
        "improvements": ["쉽게 따라 할 수 있는 개선 행동"]
      }},
      "voice": {{
        "summary": "사용자가 한 번에 이해할 수 있는 음성 특징 분석 2~3문장",
        "strengths": ["쉽게 풀어 쓴 강점"],
        "improvements": ["쉽게 따라 할 수 있는 개선 행동"]
      }}
    }}
  ]
}}"""


def _build_stage1_user(per_question: list) -> str:
    # 질문 문구마저 모델의 판단에 영향을 주지 않도록 구간 라벨은 전송하지 않는다.
    model_input = [
        {key: value for key, value in item.items() if key != "question_label"}
        for item in per_question
    ]
    return "다음은 질문 구간별 음성·비전 실측 특징입니다.\n\n" + json.dumps(
        model_input, ensure_ascii=False, indent=2
    )


def _run_stage1(client, per_question: list) -> list:
    if not per_question:
        return []
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _STAGE1_SYSTEM},
            {"role": "user", "content": _build_stage1_user(per_question)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    by_index = {q.get("index"): q for q in data.get("questions", []) if isinstance(q, dict)}

    result = []
    for pq in per_question:
        q = by_index.get(pq["index"], {})
        result.append({
            "index": pq["index"],
            "question_label": pq["question_label"],
            "start_sec": pq["start_sec"],
            "end_sec": pq["end_sec"],
            "vision": q.get("vision", {}) or {},
            "voice": q.get("voice", {}) or {},
            "metrics": {k: v for k, v in pq.items()
                        if k not in ("question_label", "index", "start_sec", "end_sec")},
        })
    return result


# ── 3. 2단계: 종합 리포트 ────────────────────────────────────────────────────

_STAGE2_SYSTEM = f"""당신은 음성·비전 기반 면접 태도 코치입니다. 아래 제공되는
(a) 전체 측정 특징, (b) 질문 구간별 태도 분석만 근거로 리포트를 작성하세요.

{EVAL_CRITERIA}

핵심 규칙:
- 답변 내용, 논리, 경험, 직무 전문성은 평가하지 마세요. 범위는 오직 말하는 방식과 보이는 태도입니다.
- 비전 분석과 행동 패턴은 시선·표정·자세만, 음성 분석은 속도·침묵·습관어·더듬음·음량만 사용하세요.
- 행동 패턴은 질문별 비전 수치에서 반복 또는 변화가 확인될 때만 작성하세요. 인과관계나 심리를 단정하지 마세요.
- 같은 조언을 여러 칸에서 반복하지 말고 핵심 수치만 자연스럽게 녹이세요.
- 사용자가 점수표를 직접 해석하게 만들지 마세요. 결론을 일상적인 표현으로 먼저 설명하세요.
- 숫자는 꼭 필요한 대표 근거만 문단당 하나 이하로 사용하고, 기준값과 측정값을 연달아 나열하지 마세요.
- "평균 88점, 기준 85점, 정면 응시 29%" 같은 보고서식 문장 대신 "자세는 비교적 안정적이지만 시선이 자주 화면 밖으로 향했습니다"처럼 쓰세요.
- 전문 용어, 판정표 문체, 과도한 괄호와 콜론을 피하고 사용자가 읽자마자 행동을 떠올릴 수 있게 쓰세요.
- spm, CV, deviation 같은 내부 지표명은 결과 문장에 쓰지 말고 각각 말의 빠르기, 목소리 크기 변화, 시선 이탈처럼 풀어 쓰세요.
- 강점과 보완점의 evidence도 숫자 목록이 아니라 실제 관찰을 짧고 자연스럽게 설명하세요.
- 개선 과제는 반복성·전달 영향·연습 가능성을 기준으로 3개 이내로 고르세요.
- 훈련 계획은 혼자 반복할 수 있게 횟수, 시간, 확인 기준을 구체화하세요.
- AI 특유의 과장과 상투어를 피하고, 영상을 함께 본 코치처럼 담백한 한국어로 쓰세요.

출력 JSON 스키마:
{{
  "modality_analysis": {{
    "vision": "평가된 시선·표정·자세 특징 기반 분석 3~4문장",
    "voice": "평가된 속도·침묵·습관어·더듬음·음량 특징 기반 분석 3~4문장"
  }},
  "executive_summary": {{
    "overall_evaluation": "음성과 비전을 아우른 종합 면접 태도 진단 3~4문장",
    "key_strengths": [{{"point": "", "evidence": ""}}],
    "key_weaknesses": [{{"point": "", "evidence": ""}}],
    "priority_area": "가장 먼저 바꿀 한 가지와 이유"
  }},
  "competency_assessment": {{
    "vision": "시선·표정·자세를 한 흐름으로 쉽게 풀어 쓴 비전 역량 평가",
    "voice": "속도·리듬·침묵·습관어·음량을 한 흐름으로 쉽게 풀어 쓴 음성 역량 평가"
  }},
  "priority_improvements": [
    {{"title": "", "rationale": "", "action": "", "success_criteria": ""}}
  ],
  "training_plan": [
    {{"goal": "", "method": "", "frequency": "", "check_criteria": ""}}
  ]
}}"""


def _build_stage2_user(overall: dict, stage1: list) -> str:
    stage1_compact = [
        {
            "index": q["index"],
            "metrics": q["metrics"],
            "vision": q["vision"], "voice": q["voice"],
        }
        for q in stage1
    ]
    return (
        "[전체 측정 특징]\n" + json.dumps(overall, ensure_ascii=False, indent=2) +
        "\n\n[질문 구간별 태도 분석]\n" + json.dumps(stage1_compact, ensure_ascii=False, indent=2)
    )


def _run_stage2(client, overall: dict, stage1: list) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _STAGE2_SYSTEM},
            {"role": "user", "content": _build_stage2_user(overall, stage1)},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


_VISION_PATTERN_SYSTEM = """당신은 면접 영상에서 보이는 행동만 분석하는 코치입니다.
입력에는 시선·표정·자세 특징만 제공됩니다. 질문별로 반복되거나 후반에 달라지는 비전 행동 패턴을 찾으세요.

규칙:
- 시선, 표정, 자세 이외의 내용은 절대 쓰지 마세요.
- 말의 속도, 침묵, 습관어, 더듬음, 음량, 목소리, 답변 내용은 언급하지 마세요.
- 두 질문 이상에서 반복되거나 질문 사이 변화가 확인되는 경우만 패턴으로 작성하세요.
- 심리나 성격을 단정하지 말고 영상에서 관찰되는 행동만 말하세요.
- 수치를 나열하지 말고 사용자가 영상을 다시 볼 때 알아차릴 수 있는 쉬운 표현으로 쓰세요.
- 각 패턴은 관찰, 근거, 바로 해볼 행동이 서로 반복되지 않게 작성하세요.

출력 JSON:
{
  "patterns": [
    {"observation": "반복되거나 달라진 비전 행동", "evidence": "질문 구간에서 확인된 근거", "coaching": "구체적인 교정 행동"}
  ],
  "note": "반복 패턴을 판단할 자료가 부족할 때만 작성"
}"""


def _run_vision_patterns(client, overall: dict, stage1: list) -> dict:
    vision_keys = ("gaze_", "expression_", "posture_")
    vision_overall = {
        key: value for key, value in overall.items()
        if key.startswith(vision_keys)
    }
    vision_scores = {
        key: value for key, value in (overall.get("scores_0to100") or {}).items()
        if key in ("시선처리", "표정안정성", "자세안정성")
    }
    questions = []
    for item in stage1:
        questions.append({
            "index": item["index"],
            "vision_features": {
                key: value for key, value in item["metrics"].items()
                if key.startswith(vision_keys)
            },
            "vision_analysis": item.get("vision", {}),
        })

    if not questions:
        return {"patterns": [], "note": "질문별 비전 구간이 없어 반복 패턴을 판단하기 어렵습니다."}

    payload = {
        "vision_scores": vision_scores,
        "overall_vision_features": vision_overall,
        "per_question_vision": questions,
    }
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _VISION_PATTERN_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    return {
        "patterns": data.get("patterns", []) or [],
        "note": data.get("note", ""),
    }


# ── 4. 엔트리포인트 ──────────────────────────────────────────────────────────

def generate_deep_report(job: dict) -> Optional[dict]:
    """
    Returns
    -------
    {
      "cross_modal": {...},               # 교차집계 원본(디버그/프론트 참고용)
      "per_question": [...],              # 1단계 결과
      "executive_summary": {...},
      "competency_assessment": {...},
      "behavior_pattern_analysis": {...},
      "priority_improvements": [...],
      "training_plan": [...],
    }
    실패 시 None. (기존 scores 등 분석 결과는 건드리지 않음)
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[DeepReport] OPENAI_API_KEY 없음 — 생성 생략")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        cross = build_cross_modal_data(job)
        print(f"[DeepReport] 1단계(질문별 {len(cross['per_question'])}개) 호출 중...")
        stage1 = _run_stage1(client, cross["per_question"])

        print("[DeepReport] 2단계(종합) 호출 중...")
        stage2 = _run_stage2(client, cross["overall"], stage1)

        print("[DeepReport] 3단계(비전 행동 패턴) 호출 중...")
        vision_patterns = _run_vision_patterns(client, cross["overall"], stage1)

        return {
            "report_version": REPORT_VERSION,
            "cross_modal": cross,
            "per_question": stage1,
            **stage2,
            "behavior_pattern_analysis": vision_patterns,
        }
    except Exception as e:
        print(f"[DeepReport] 생성 실패: {e}")
        return None
