"""
ngram_model.py
--------------
NLTK 기반 N-gram 언어 모델.

변경 이력
---------
v2: KoNLPy 형태소 단위 토크나이징 지원 (tokenize 함수 교체)
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# 토크나이저
# ---------------------------------------------------------------------------

def _fallback_tokenize(text: str) -> list[str]:
    """KoNLPy 미설치 환경용 공백 기반 토크나이저."""
    text = text.strip().lower()
    text = re.sub(r"([,.!?。、！？])", r" \1 ", text)
    return [t for t in text.split() if t]


def make_tokenizer(analyzer: str = "okt", use_pos: bool = True):
    """
    KoNLPy 형태소 분석기를 래핑한 tokenize 함수를 반환합니다.

    Parameters
    ----------
    analyzer : str
        사용할 분석기 이름. 'okt' | 'komoran' | 'kkma' | 'hannanum'
        (속도: okt > komoran > kkma, 정확도: kkma > komoran > okt)
    use_pos : str
        True  → 토큰을 "어절__품사" 형태로 반환 (품사 정보 보존)
        False → 어절 표면형만 반환

    Returns
    -------
    tokenize : callable
        (text: str) -> list[str]
    tagger : KoNLPy tagger instance (재사용 가능하도록 반환)
    """
    try:
        if analyzer == "okt":
            from konlpy.tag import Okt
            tagger = Okt()
            pos_fn = lambda t: tagger.pos(t, norm=True, stem=False)
        elif analyzer == "komoran":
            from konlpy.tag import Komoran
            tagger = Komoran()
            pos_fn = tagger.pos
        elif analyzer == "kkma":
            from konlpy.tag import Kkma
            tagger = Kkma()
            pos_fn = tagger.pos
        elif analyzer == "hannanum":
            from konlpy.tag import Hannanum
            tagger = Hannanum()
            pos_fn = tagger.pos
        else:
            raise ValueError(f"지원하지 않는 분석기: {analyzer}")

        if use_pos:
            def tokenize(text: str) -> list[str]:
                return [f"{morph}__{tag}" for morph, tag in pos_fn(text)]
        else:
            def tokenize(text: str) -> list[str]:
                return [morph for morph, _ in pos_fn(text)]

        print(f"[Tokenizer] KoNLPy {analyzer} 로드 완료 (use_pos={use_pos})")
        return tokenize, tagger

    except ImportError:
        print("[Tokenizer] KoNLPy 미설치 → 공백 기반 fallback 사용")
        return _fallback_tokenize, None
    except Exception as e:
        print(f"[Tokenizer] KoNLPy 초기화 실패 ({e}) → fallback 사용")
        return _fallback_tokenize, None


# ---------------------------------------------------------------------------
# N-gram 언어 모델
# ---------------------------------------------------------------------------

class NgramLanguageModel:
    """
    Add-k(라플라스) 스무딩을 적용한 N-gram 언어 모델.

    Parameters
    ----------
    n : int
        N-gram 차수 (기본값 3)
    k : float
        라플라스 스무딩 상수 (기본값 0.1)
    tokenize_fn : callable | None
        외부에서 주입하는 토크나이저. None이면 공백 기반 fallback 사용.
    """

    BOS = "<s>"
    EOS = "</s>"

    def __init__(self, n: int = 3, k: float = 0.1, tokenize_fn=None):
        self.n = n
        self.k = k
        self._tokenize = tokenize_fn or _fallback_tokenize
        self._counts: dict[tuple, int] = defaultdict(int)
        self._context_counts: dict[tuple, int] = defaultdict(int)
        self._vocab: set[str] = set()
        self._trained = False

    # ------------------------------------------------------------------
    # 학습
    # ------------------------------------------------------------------

    def train(self, sentences: Iterable[str]) -> "NgramLanguageModel":
        for sent in sentences:
            tokens = self._pad(self._tokenize(sent))
            self._vocab.update(tokens)
            for i in range(len(tokens) - self.n + 1):
                ngram = tuple(tokens[i: i + self.n])
                context = ngram[:-1]
                self._counts[ngram] += 1
                self._context_counts[context] += 1

        self._vocab.discard(self.BOS)
        self._vocab.discard(self.EOS)
        self._trained = True
        return self

    def train_from_file(self, path: str | Path) -> "NgramLanguageModel":
        """텍스트 파일(줄 단위 문장)로부터 학습합니다."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            self.train(line.strip() for line in f if line.strip())
        return self

    # ------------------------------------------------------------------
    # 확률 계산
    # ------------------------------------------------------------------

    def token_logprob(self, token: str, context: tuple[str, ...]) -> float:
        self._check_trained()
        vocab_size = len(self._vocab) + 1
        ctx = self._normalize_context(context)
        ngram = ctx + (token,)
        numerator = self._counts[ngram] + self.k
        denominator = self._context_counts[ctx] + self.k * vocab_size
        return math.log10(numerator / denominator)

    def sequence_logprob(self, sentence: str) -> float:
        self._check_trained()
        tokens = self._pad(self._tokenize(sentence))
        total = 0.0
        for i in range(self.n - 1, len(tokens)):
            token = tokens[i]
            context = tuple(tokens[i - (self.n - 1): i])
            total += self.token_logprob(token, context)
        return total

    def perplexity(self, sentence: str) -> float:
        tokens = self._tokenize(sentence)
        if not tokens:
            return float("inf")
        log_prob = self.sequence_logprob(sentence)
        return 10 ** (-log_prob / len(tokens))

    def token_surprise(self, token: str, context: tuple[str, ...]) -> float:
        return -self.token_logprob(token, context)

    # ------------------------------------------------------------------
    # 내부 유틸
    # ------------------------------------------------------------------

    def _pad(self, tokens: list[str]) -> list[str]:
        return [self.BOS] * (self.n - 1) + tokens + [self.EOS]

    def _normalize_context(self, context: tuple[str, ...]) -> tuple[str, ...]:
        ctx = context[-(self.n - 1):]
        while len(ctx) < self.n - 1:
            ctx = (self.BOS,) + ctx
        return ctx

    def _check_trained(self):
        if not self._trained:
            raise RuntimeError("모델이 아직 학습되지 않았습니다. train()을 먼저 호출하세요.")

    # ------------------------------------------------------------------
    # 직렬화
    # ------------------------------------------------------------------

    def save(self, path: str | Path):
        import pickle
        # tokenize_fn은 pickle 불가 → 저장 전 제거, 로드 후 재주입
        tokenize_fn = self._tokenize
        self._tokenize = None
        with open(path, "wb") as f:
            pickle.dump(self, f)
        self._tokenize = tokenize_fn  # 저장 후 복원
        print(f"[NgramLM] 저장 완료: {path}")

    @classmethod
    def load(cls, path: str | Path) -> "NgramLanguageModel":
        import pickle
        with open(path, "rb") as f:
            model = pickle.load(f)
        print(f"[NgramLM] 로드 완료: {path}")
        return model

    def __repr__(self):
        return (
            f"NgramLanguageModel(n={self.n}, k={self.k}, "
            f"vocab_size={len(self._vocab)}, trained={self._trained})"
        )
