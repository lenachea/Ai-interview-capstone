"""
report_generator.py
-------------------
평가모델이 낸 7개 항목 점수 + 음성/비전 원본 지표를 GPT-4o에 넘겨
사용자가 읽을 "상세 리포트"(자연어)를 생성한다.

기존 ResultsDetail.jsx의 규칙 기반 문구(if spm > 350 → "빠릅니다")는 그대로 두고,
이 리포트를 별도 섹션으로 추가하는 용도. API 키가 없거나 호출이 실패하면
None을 반환하고, 프론트엔드는 해당 섹션을 그냥 숨긴다.
"""
from __future__ import annotations

import json
import os
from typing import Optional

MODEL = "gpt-5.6-sol"

SYSTEM_PROMPT = """당신은 모의면접 결과를 분석해 피드백을 작성하는 면접 코치입니다.
주어진 분석 데이터(점수와 객관적 지표)만 근거로 리포트를 작성하세요.

[이 시스템의 평가 기준 — 조언은 반드시 이 기준에 맞출 것]
- 발화 속도: 분당 270~350음절이 적정. 270 미만은 느림, 350 초과는 빠름.
- 정면 응시 비율: 0.8 이상이면 안정적, 0.6~0.8은 가끔 이탈, 0.6 미만은 시선 회피가 잦음.
- 자세 점수: 100점 만점이며 95 이상이면 매우 안정적, 85 미만이면 개선 필요.
- 점수(0~100점)는 36개 모의면접 영상을 사람이 채점한 데이터로 학습한 모델의 예측값.

규칙:
- 데이터에 없는 내용(답변 내용의 논리성, 표정의 구체적 의미 등)은 추측하지 마세요.
- 점수가 낮은 항목은 왜 낮게 나왔는지 해당 지표를 인용해 설명하고, 구체적인 개선 행동을 제시하세요.
- 점수가 높은 항목은 짧게 칭찬만 하고 넘어가세요.
- 숫자를 인용할 때는 단위를 함께 쓰세요(예: 분당 320음절, 2회).
- 목표 수치를 제시할 때는 위 평가 기준의 숫자를 그대로 쓰세요. 임의의 목표치를 지어내지 마세요.
- 과장하거나 단정하지 말고, 면접 준비에 실제로 도움이 되는 톤으로 쓰세요.
- 전체 분량은 400~600자 내외의 한국어로 작성하세요."""


def _build_user_prompt(payload: dict) -> str:
    return f"""다음은 한 지원자의 모의면접 분석 결과입니다.

[항목별 점수 (0~100점)]
{json.dumps(payload.get("scores", {}), ensure_ascii=False, indent=2)}

[음성 지표]
{json.dumps(payload.get("speech", {}), ensure_ascii=False, indent=2)}

[비전 지표]
{json.dumps(payload.get("vision", {}), ensure_ascii=False, indent=2)}

아래 JSON 형식으로만 답하세요:
{{
  "overall": "종합 총평 2~3문장",
  "strengths": ["잘한 점 1", "잘한 점 2"],
  "improvements": [
    {{"item": "항목명", "why": "이 점수가 나온 이유를 지표 인용해 설명", "action": "구체적 개선 행동"}}
  ]
}}"""


def _extract_payload(scores: dict, language_analysis: dict, nonverbal_analysis: dict) -> dict:
    metrics = (language_analysis or {}).get("metrics", {}) or {}
    raw = (language_analysis or {}).get("raw_data", {}) or {}
    nv = nonverbal_analysis or {}
    gaze = nv.get("gaze_summary", {}) or {}
    expr = nv.get("expression_summary", {}) or {}
    posture = nv.get("posture_summary", {}) or {}

    return {
        "scores": scores or {},
        "speech": {
            "분당_음절수": metrics.get("speech_rate", {}).get("spm"),
            "속도_평가": metrics.get("speech_rate", {}).get("label"),
            "습관어_횟수": metrics.get("filler_word", {}).get("count"),
            "더듬음_횟수": metrics.get("stuttering", {}).get("count"),
            "긴침묵_횟수": metrics.get("long_pauses", {}).get("count"),
            "음량_상태": metrics.get("volume_stability", {}).get("label"),
            "총_발화시간_초": raw.get("total_duration_sec"),
            "순수_발화시간_초": raw.get("pure_speech_time_sec"),
        },
        "vision": {
            "정면응시_비율": gaze.get("gaze_ratio"),
            "시선이탈_구간수": len(nv.get("gaze_deductions", []) or []),
            "주요표정": expr.get("dominant_emotion"),
            "긍정표정_비율": expr.get("positive_ratio"),
            "부정표정_비율": expr.get("negative_ratio"),
            "표정흔들림_구간수": len(nv.get("expression_deductions", []) or []),
            "자세점수_평균": posture.get("score_mean"),
            "구부정_횟수": posture.get("slouch_count"),
        },
    }


def generate_report(scores: dict,
                     language_analysis: dict,
                     nonverbal_analysis: dict) -> Optional[dict]:
    """
    Returns
    -------
    {"overall": str, "strengths": [str], "improvements": [{"item","why","action"}]}
    실패 시 None.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[Report] OPENAI_API_KEY 없음 — 상세 리포트 생략")
        return None

    try:
        from openai import OpenAI

        payload = _extract_payload(scores, language_analysis, nonverbal_analysis)
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(payload)},
            ],
            response_format={"type": "json_object"},
        )
        report = json.loads(resp.choices[0].message.content)

        # 형식 방어 — 기대한 키가 없으면 빈 값으로 채운다
        return {
            "overall": str(report.get("overall", "")),
            "strengths": [str(s) for s in (report.get("strengths") or [])],
            "improvements": [
                {
                    "item": str(x.get("item", "")),
                    "why": str(x.get("why", "")),
                    "action": str(x.get("action", "")),
                }
                for x in (report.get("improvements") or [])
                if isinstance(x, dict)
            ],
        }
    except Exception as e:
        print(f"[Report] 생성 실패: {e}")
        return None
