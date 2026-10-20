"""
corrected_frame.py
------------------
표정/시선/자세별로 가장 문제가 큰 실제 프레임 두 장을 함께 입력받아, 두 장의 공통적인
문제만 교정한 개선 레퍼런스 이미지 한 장을 생성한다. 타임라인 클릭과는 분리되어 있고
사용자가 "개선 레퍼런스 이미지 보기"를 눌렀을 때만 카테고리별로 한 번 생성한다.
"""
from __future__ import annotations

import base64
import io
import os
import threading
from pathlib import Path
from typing import Callable, Optional

MODEL = "gpt-image-2.5-sunburst"

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}

_BASE = (
    "The attached image is a side-by-side comparison containing two frames of the same job "
    "interview candidate from the same video. Use both halves as visual references. Create one "
    "photorealistic corrected reference frame, not another split-screen comparison. "
    "Keep the exact same person, face, glasses, hairstyle, clothing, chair, room, background, "
    "lighting and camera framing. Choose the clearer source frame as the composition base. "
)
_TAIL = "Do not change anything else. Photorealistic, no text."

# 카테고리 → 바꿀 한 가지
CHANGES = {
    "posture": (
        "Change ONLY the posture: the person now sits upright with back straight, shoulders level and "
        "relaxed, head raised and centered over the shoulders, chin level, facing the camera. "
    ),
    "gaze": (
        "Change ONLY the gaze: the person now looks straight into the camera lens with steady, "
        "confident eye contact, head facing the camera. "
    ),
    "expression": (
        "Change ONLY the facial expression: calm, relaxed, pleasant and natural, relaxed eyebrows, "
        "a slight friendly smile, looking attentive. "
    ),
}


def _prompt(group: str) -> str:
    return _BASE + CHANGES[group] + _TAIL


def cache_path(job_dir: Path, group: str) -> Path:
    return job_dir / "corrected" / f"{group}_reference_v2.png"


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _combine_frames(frames: list[bytes]) -> bytes:
    """구버전 SDK의 단일 image 입력에 맞춰 최대 두 프레임을 좌우 비교 이미지로 합친다."""
    from PIL import Image

    images = [Image.open(io.BytesIO(frame)).convert("RGB") for frame in frames[:2]]
    target_height = min(768, *(image.height for image in images))
    resized = []
    for image in images:
        width = max(1, round(image.width * target_height / image.height))
        resized.append(image.resize((width, target_height), Image.Resampling.LANCZOS))

    canvas = Image.new("RGB", (sum(image.width for image in resized), target_height), "white")
    offset = 0
    for image in resized:
        canvas.paste(image, (offset, 0))
        offset += image.width

    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def get_corrected_reference(
    job_dir: Path,
    group: str,
    times: list[float],
    get_frames: Callable[[], list[bytes]],
) -> Optional[Path]:
    """
    두 문제 장면 기반 개선 이미지 경로를 반환한다. 실패하면 None.
    get_frames는 캐시가 없을 때만 호출되며 1~2장의 JPEG bytes를 반환한다.
    """
    if group not in CHANGES:
        return None

    if not times:
        return None

    path = cache_path(job_dir, group)
    if path.exists():
        return path

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[Corrected] OPENAI_API_KEY 없음 — 개선 예시 생략")
        return None

    # 같은 구간을 동시에 여러 번 요청해도 한 번만 생성
    with _lock_for(str(path)):
        if path.exists():
            return path
        try:
            from openai import OpenAI

            frames = get_frames()
            if not frames:
                return None
            comparison = _combine_frames(frames)
            client = OpenAI(api_key=api_key)
            resp = client.images.edit(
                model=MODEL,
                image=("problem_pair.jpg", comparison, "image/jpeg"),
                prompt=_prompt(group),
            )
            image_bytes = base64.b64decode(resp.data[0].b64_json)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            print(f"[Corrected] {group} 대표 문제 장면 {len(frames[:2])}개 기반 생성 완료 → {path}")
            return path
        except Exception as e:
            print(f"[Corrected] {group} 개선 레퍼런스 생성 실패: {e}")
            return None
