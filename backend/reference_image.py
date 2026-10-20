"""
reference_image.py
------------------
문제 구간(자세/시선/표정) 옆에 보여줄 "좋은 예시" 레퍼런스 이미지를
gpt-image-1으로 생성하고 디스크에 캐시한다.

사용자 개개인의 얼굴을 합성하는 게 아니라 카테고리별 일반 예시 일러스트라서,
전체 서비스에서 카테고리당 1장만 있으면 된다 → 최초 1회만 생성하고 이후 캐시 재사용
(= API 비용이 사용자 수와 무관하게 고정).
"""
from __future__ import annotations

import base64
import os
import threading
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).parent / "reference_images"
MODEL = "gpt-image-2.5-sunburst"
_lock = threading.Lock()

# 카테고리 → 생성 프롬프트
PROMPTS = {
    "posture": (
        "A clean flat vector illustration of a job interview candidate sitting upright with "
        "excellent posture: back straight, shoulders level and relaxed, head balanced over the "
        "shoulders, facing the camera directly. Waist-up front view, plain light background. "
        "Simple minimal style, no text, no letters, no words, no watermark."
    ),
    "gaze": (
        "A clean flat vector illustration of a job interview candidate looking straight into the "
        "camera with steady, confident eye contact. Waist-up front view, eyes clearly directed "
        "forward at the viewer, plain light background. Simple minimal style, "
        "no text, no letters, no words, no watermark."
    ),
    "expression": (
        "A clean flat vector illustration of a job interview candidate with a calm, pleasant, "
        "natural facial expression: relaxed eyebrows and a slight friendly smile, looking "
        "attentive and composed. Waist-up front view, plain light background. "
        "Simple minimal style, no text, no letters, no words, no watermark."
    ),
}

LABELS = {
    "posture": "바른 자세 예시",
    "gaze": "안정적인 시선 처리 예시",
    "expression": "자연스러운 표정 예시",
}


def cached_path(category: str) -> Path:
    return CACHE_DIR / f"{category}.png"


def get_reference_image(category: str) -> Optional[Path]:
    """
    카테고리("posture"/"gaze"/"expression")의 레퍼런스 이미지 경로를 반환.
    캐시에 없으면 생성해서 저장한 뒤 반환. 실패하면 None.
    """
    if category not in PROMPTS:
        return None

    path = cached_path(category)
    if path.exists():
        return path

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[RefImage] OPENAI_API_KEY 없음 — 레퍼런스 이미지 생략")
        return None

    # 동시 요청이 같은 이미지를 중복 생성하지 않도록
    with _lock:
        if path.exists():
            return path
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            resp = client.images.generate(
                model=MODEL,
                prompt=PROMPTS[category],
                size="1024x1024",
                n=1,
            )
            image_bytes = base64.b64decode(resp.data[0].b64_json)

            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            print(f"[RefImage] {category} 생성 완료 → {path}")
            return path
        except Exception as e:
            print(f"[RefImage] {category} 생성 실패: {e}")
            return None
