"""
prepare_corpus.py
-----------------
AI Hub 모의면접 답변 txt 파일을 N-gram 학습용 코퍼스로 전처리합니다.

입력: 답변이 단락 단위로 들어있는 txt 파일
출력: 줄 단위 문장 파일 (train_from_file()에 바로 사용 가능)

실행:
    python prepare_corpus.py
    python prepare_corpus.py --input data/raw_answers.txt --output data/corpus.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# 문장 분리 기준
# 한국어는 마침표/물음표/느낌표 외에도 줄바꿈으로 단락이 구분되는 경우가 많으므로
# 두 기준을 모두 사용합니다.
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    """
    단락 텍스트를 문장 단위로 분리합니다.
    N-gram 학습 목적이므로 filler word는 제거하지 않습니다.
    """
    # 1. 줄바꿈 기준 1차 분리
    lines = text.splitlines()

    sentences = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 2. 문장 종결 부호 기준 2차 분리
        # '.' '?' '!' '요' '니다' '습니다' 뒤를 기준으로 분리
        parts = re.split(r'(?<=[.?!])\s+', line)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)

    return sentences


def clean_sentence(sent: str) -> str:
    """
    최소한의 정제만 수행합니다.
    - 앞뒤 공백 제거
    - 연속 공백 → 단일 공백
    - 특수문자 중 의미 없는 것만 제거 (한글/영문/숫자/기본 문장부호 유지)

    filler word('어', '음', '그' 등)는 N-gram 학습 목적상 유지합니다.
    """
    sent = sent.strip()
    sent = re.sub(r'\s+', ' ', sent)
    # 한글, 영문, 숫자, 공백, 기본 문장부호만 유지
    sent = re.sub(r'[^\w\s가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9.,?!]', '', sent)
    sent = sent.strip()
    return sent


def is_valid(sent: str, min_chars: int = 5) -> bool:
    """
    너무 짧거나 한글이 없는 문장 제외.
    """
    if len(sent) < min_chars:
        return False
    if not re.search(r'[가-힣]', sent):
        return False
    return True


def process(input_path: str, output_path: str, min_chars: int = 5) -> None:
    input_p  = Path(input_path)
    output_p = Path(output_path)
    output_p.parent.mkdir(parents=True, exist_ok=True)

    raw_text = input_p.read_text(encoding="utf-8")

    sentences = split_sentences(raw_text)
    cleaned   = [clean_sentence(s) for s in sentences]
    valid     = [s for s in cleaned if is_valid(s, min_chars)]

    # 중복 제거 (순서 유지)
    seen = set()
    deduped = []
    for s in valid:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    output_p.write_text("\n".join(deduped), encoding="utf-8")

    print(f"[완료]")
    print(f"  원본 단락 수     : {len(raw_text.splitlines())}")
    print(f"  분리된 문장 수   : {len(sentences)}")
    print(f"  정제 후 유효 문장: {len(valid)}")
    print(f"  중복 제거 후     : {len(deduped)}")
    print(f"  저장 경로        : {output_p}")


# ---------------------------------------------------------------------------
# 샘플 미리보기
# ---------------------------------------------------------------------------

def preview(output_path: str, n: int = 10) -> None:
    lines = Path(output_path).read_text(encoding="utf-8").splitlines()
    print(f"\n[샘플 {n}개]")
    for line in lines[:n]:
        print(f"  {line}")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",     default="data/raw_answers.txt", help="원본 txt 파일 경로")
    parser.add_argument("--output",    default="data/corpus.txt",      help="출력 코퍼스 파일 경로")
    parser.add_argument("--min_chars", default=5, type=int,            help="최소 문장 길이 (기본 5자)")
    parser.add_argument("--preview",   default=10, type=int,           help="미리보기 문장 수")
    args = parser.parse_args()

    process(args.input, args.output, args.min_chars)
    preview(args.output, args.preview)