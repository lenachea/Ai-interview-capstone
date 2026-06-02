"""
analyzers/transcriber.py
------------------------
faster-whisper STT 담당 모듈 (로컬 추론, medium 모델).
"""

from __future__ import annotations

PROMPT_HINT = (
    "한국어 면접 녹음입니다. "
    "질문자와 응시자가 번갈아 발화합니다. "
    "응시자 답변 예시: '저의 강점은 책임감입니다. 약점은 완벽주의 성향입니다.' "
    "'어', '음', '그', '저', '뭐', '이제', '그냥', '좀', '근데', '아' 같은 "
    "간투사와 습관어를 생략하지 말고 발화된 그대로 전사해 주세요. "
    "발음이 불명확해도 문맥에 맞는 단어로 전사하세요."
)


def load_model(model_size: str = "medium"):
    """faster-whisper WhisperModel을 반환합니다. 최초 호출 시 모델 다운로드."""
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(model, audio_path: str) -> tuple[str, list[dict]]:
    full_text, words_info, _ = transcribe_with_segments(model, audio_path)
    return full_text, words_info


def transcribe_with_segments(model, audio_path: str) -> tuple[str, list[dict], list[dict]]:
    """
    Returns
    -------
    full_text : str
    words_info : list[dict]
        [{"word": str, "start": float, "end": float}, ...]
    segments_info : list[dict]
        [{"start": float, "end": float, "text": str}, ...]
        GPT Q&A 분리에 사용됩니다.
    """
    segments_gen, _ = model.transcribe(
        audio_path,
        language="ko",
        word_timestamps=True,
        initial_prompt=PROMPT_HINT,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
        no_speech_threshold=0.5,
    )

    words_info: list[dict] = []
    segments_info: list[dict] = []
    text_parts: list[str] = []

    for seg in segments_gen:
        text_parts.append(seg.text)
        segments_info.append({
            "start": round(seg.start, 3),
            "end":   round(seg.end,   3),
            "text":  seg.text.strip(),
        })
        for w in (seg.words or []):
            words_info.append({
                "word":  w.word.strip(),
                "start": w.start,
                "end":   w.end,
            })

    return "".join(text_parts).strip(), words_info, segments_info
