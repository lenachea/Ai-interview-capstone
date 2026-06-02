"""
qa_splitter.py
--------------
GPT-4o-mini를 사용해 STT 세그먼트에서 질문/답변 경계를 찾아
각 답변의 타임스탬프를 반환합니다.
"""
from __future__ import annotations

import json
import os


def find_answer_segments(
    segments_info: list[dict],
    questions: list[str],
) -> list[dict]:
    """
    Parameters
    ----------
    segments_info : list[dict]
        [{"start": float, "end": float, "text": str}]
    questions : list[str]
        고정 면접 질문 목록

    Returns
    -------
    list[dict]
        [{"index": int, "question": str, "question_start": float,
          "start": float, "end": float}]
        찾지 못한 질문은 제외됩니다.
        실패 시 빈 리스트 반환 → 호출자가 fallback 처리.
    """
    if not segments_info or not questions:
        return []

    timed_transcript = "\n".join(
        f"[{seg['start']:.1f}s] {seg['text']}"
        for seg in segments_info
    )
    questions_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    last_end = segments_info[-1]["end"]

    user_prompt = f"""아래 면접 STT 결과에서 각 질문에 대한 응시자 답변 구간을 찾아주세요.

면접 질문 목록:
{questions_text}

STT 결과 (각 줄 앞 [시간]은 해당 세그먼트 시작 시간):
{timed_transcript}

규칙:
- 질문자가 질문을 말한 후 응시자가 답변하는 구간의 시작/끝 시간을 반환하세요.
- answer_start: 응시자 답변이 시작되는 세그먼트의 시작 시간
- answer_end: 다음 질문이 시작되기 직전 세그먼트의 끝 시간 (마지막 답변이면 {last_end:.1f})
- question_start: 질문자가 해당 질문을 말하기 시작한 시간
- 질문을 찾지 못하면 해당 항목을 결과에서 제외하세요.
- JSON만 출력하세요.

{{
  "answers": [
    {{
      "question": "질문 텍스트 원문",
      "question_start": 질문시작초,
      "answer_start": 답변시작초,
      "answer_end": 답변끝초
    }}
  ]
}}"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "면접 STT 결과에서 주어진 질문들을 찾아 "
                        "각 답변 구간의 타임스탬프를 JSON으로 반환합니다."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        raw_answers = data.get("answers", [])

        result = []
        for i, ans in enumerate(raw_answers):
            if ans.get("answer_start") is None or ans.get("answer_end") is None:
                continue
            result.append({
                "index":          i,
                "question":       str(ans.get("question", "")),
                "question_start": float(ans.get("question_start") or 0.0),
                "start":          float(ans["answer_start"]),
                "end":            float(ans["answer_end"]),
            })

        print(f"[QA Splitter] 답변 {len(result)}개 분리 완료")
        return result

    except Exception as e:
        print(f"[QA Splitter] 실패: {e}")
        return []
