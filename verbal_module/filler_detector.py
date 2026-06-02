"""
filler_detector.py
------------------
한국어 STT 결과에서 filler word를 탐지합니다.

개선 이력 (v2)
--------------
1. KoNLPy 형태소 분석 기반 품사 인식
   - 동음이의어 오탐 해결: '저(NP, 대명사)'와 '저(IC, 감탄사)'를 구분
   - 품사 allowlist/denylist로 filler 후보 필터링

2. 점수 결합 방식 개선
   - Dict/Context 점수를 결합 전 Min-Max 정규화
   - Surprisal 계산을 문장 내 상대 z-score로 변환 (코퍼스 크기 무관)
   - Removability를 단일 스텝이 아닌 윈도우 평균으로 확장

3. 도메인 적응형 α/β 조정
   - calibrate()로 레이블된 샘플을 받아 threshold를 자동 탐색
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

from ngram_model import NgramLanguageModel, _fallback_tokenize


# ---------------------------------------------------------------------------
# 한국어 Filler Word 사전
# 형태: { 표면형(소문자): (dict_score, 허용 품사 집합 or None) }
# 허용 품사가 None이면 품사 무관하게 적용 (KoNLPy 미사용 시 fallback)
# ---------------------------------------------------------------------------

# KoNLPy Okt 품사 태그 참고:
#   Noun(명사), Verb(동사), Adjective(형용사), Adverb(부사),
#   Determiner(관형사), Exclamation(감탄사), Josa(조사),
#   Eomi(어미), Suffix(접미사), Punctuation(구두점), Unknown

FILLER_DICT: dict[str, tuple[float, set[str] | None]] = {
    # 순수 간투사 — 품사 무관 (항상 filler)
    "어":     (0.95, None),
    "음":     (0.95, None),
    "아":     (0.85, None),
    "에":     (0.80, None),
    "으":     (0.80, None),
    "흠":     (0.85, None),
    "흐음":   (0.85, None),
    "뭐냐":   (0.90, None),
    "뭐랄까": (0.90, None),
    "있잖아": (0.85, None),
    "있잖아요":(0.85, None),

    # 품사 조건부 filler
    # '그', '저', '뭐'는 감탄사(Exclamation) / Unknown 일 때만 filler
    "그":     (0.70, {"Exclamation", "Unknown"}),
    "저":     (0.75, {"Exclamation", "Unknown"}),
    "뭐":     (0.80, {"Exclamation", "Unknown", "Noun"}),

    # 부사로 사용될 때 filler 가능성이 높은 어휘
    "그냥":   (0.55, {"Adverb", "Unknown"}),
    "막":     (0.65, {"Adverb", "Unknown"}),
    "약간":   (0.50, {"Adverb", "Unknown"}),
    "진짜":   (0.40, {"Adverb", "Unknown"}),
    "좀":     (0.40, {"Adverb", "Unknown"}),
    "그니까":  (0.60, {"Adverb", "Conjunction", "Unknown"}),
    "그러니까":(0.55, {"Adverb", "Conjunction", "Unknown"}),
    "근데":   (0.50, {"Adverb", "Conjunction", "Unknown"}),
    "근데요":  (0.50, {"Adverb", "Unknown"}),
    "어쨌든":  (0.45, {"Adverb", "Unknown"}),
    "일단":   (0.40, {"Adverb", "Unknown"}),
    "이제":   (0.45, {"Adverb", "Unknown"}),
    "저기":   (0.65, {"Exclamation", "Unknown"}),
}

# 절대 filler로 판정하지 않을 품사 (명사, 동사, 형용사, 조사, 어미 등)
FILLER_DENYLIST_POS = {
    "Noun", "Verb", "Adjective", "Josa", "Eomi",
    "Suffix", "Number", "KoreanParticle",
}


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class DetectedFiller:
    token: str
    pos: str                          # 품사 태그 (KoNLPy 미사용 시 "UNK")
    index: int
    dict_score: float
    context_score: float
    final_score: float
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DetectionResult:
    original_text: str
    tokens: list[str]
    pos_tags: list[str]
    fillers: list[DetectedFiller]
    cleaned_text: str
    filler_ratio: float

    def to_dict(self) -> dict:
        return {
            "original_text": self.original_text,
            "tokens": self.tokens,
            "pos_tags": self.pos_tags,
            "fillers": [f.to_dict() for f in self.fillers],
            "cleaned_text": self.cleaned_text,
            "filler_ratio": round(self.filler_ratio, 4),
        }

    def summary(self) -> str:
        lines = [
            f"[원본]    {self.original_text}",
            f"[정제]    {self.cleaned_text}",
            f"[형태소]  {list(zip(self.tokens, self.pos_tags))}",
            f"[filler] {[f.token for f in self.fillers]} "
            f"({len(self.fillers)}개 / 비율 {self.filler_ratio:.1%})",
        ]
        if self.fillers:
            lines.append("[상세]")
            for f in self.fillers:
                ts = (
                    f" [{f.start_time:.2f}s~{f.end_time:.2f}s]"
                    if f.start_time is not None else ""
                )
                lines.append(
                    f"  #{f.index:>2} '{f.token}'({f.pos}){ts}  "
                    f"dict={f.dict_score:.2f}  ctx={f.context_score:.2f}  "
                    f"final={f.final_score:.2f}"
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 탐지기
# ---------------------------------------------------------------------------

class FillerDetector:
    """
    Parameters
    ----------
    lm : NgramLanguageModel | None
    tagger : KoNLPy tagger instance | None
        None이면 품사 정보 없이 표면형만 사용 (동음이의어 구분 불가)
    alpha : float
        dict_score 가중치
    beta : float
        context_score 가중치
    threshold : float
        filler 판정 임계값
    removability_window : int
        removability 계산 시 후방으로 확인할 토큰 수 (기본 3)
    """

    def __init__(
        self,
        lm: Optional[NgramLanguageModel] = None,
        tagger=None,
        alpha: float = 0.6,
        beta: float = 0.4,
        threshold: float = 0.45,
        removability_window: int = 3,
    ):
        self.lm = lm
        self.tagger = tagger
        self.alpha = alpha
        self.beta = beta
        self.threshold = threshold
        self.removability_window = removability_window

        if lm is None:
            self.alpha, self.beta = 1.0, 0.0

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def detect(
        self,
        text: str,
        word_timestamps: Optional[list[dict]] = None,
    ) -> DetectionResult:
        """
        Parameters
        ----------
        text : str
            STT 결과 문자열
        word_timestamps : list[dict] | None
            Whisper word-level timestamps 호환:
            [{"word": str, "start": float, "end": float}, ...]
        """
        # 1. 형태소 분석
        morph_pos = self._pos_tag(text)
        if not morph_pos:
            return DetectionResult(text, [], [], [], "", 0.0)

        tokens = [m for m, _ in morph_pos]
        pos_tags = [p for _, p in morph_pos]
        ts_map = _build_timestamp_map(word_timestamps or [])
        ts_counter: dict[str, int] = {}  # 단어별 사용 횟수 추적

        # 2. 문장 전체 surprisal 분포 계산 (z-score 정규화용)
        surprisals = self._compute_surprisals(tokens)

        # 3. 토큰별 점수 계산
        fillers: list[DetectedFiller] = []
        for i, (token, pos) in enumerate(morph_pos):
            # FILLER_DICT 조회를 먼저 수행 — dict에 명시된 POS라면 denylist 우선순위보다 높음
            dict_score = self._dict_score(token, pos)
            if dict_score == 0.0 and pos in FILLER_DENYLIST_POS:
                continue

            ctx_score = self._context_score_normalized(
                token, tokens, i, surprisals
            )

            dict_score = max(0.0, min(1.0, dict_score))
            ctx_score = max(0.0, min(1.0, ctx_score))

            final = self.alpha * dict_score + self.beta * ctx_score

            if final >= self.threshold:
                surface = token.lower()
                ts_list = ts_map.get(surface, [])
                idx = ts_counter.get(surface, 0)
                # 이미 사용한 횟수만큼 건너뛰어 해당 출현의 타임스탬프 선택
                ts = ts_list[idx] if idx < len(ts_list) else (ts_list[-1] if ts_list else None)
                ts_counter[surface] = idx + 1
                fillers.append(DetectedFiller(
                    token=token,
                    pos=pos,
                    index=i,
                    dict_score=round(dict_score, 4),
                    context_score=round(ctx_score, 4),
                    final_score=round(final, 4),
                    start_time=ts[0] if ts else None,
                    end_time=ts[1] if ts else None,
                ))

        filler_indices = {f.index for f in fillers}
        cleaned = " ".join(t for i, t in enumerate(tokens) if i not in filler_indices)

        return DetectionResult(
            original_text=text,
            tokens=tokens,
            pos_tags=pos_tags,
            fillers=fillers,
            cleaned_text=cleaned,
            filler_ratio=len(fillers) / len(tokens) if tokens else 0.0,
        )

    def detect_batch(self, texts: list[str]) -> list[DetectionResult]:
        return [self.detect(t) for t in texts]

    def calibrate(
        self,
        labeled_samples: list[tuple[str, list[int]]],
        search_range: tuple[float, float] = (0.3, 0.8),
        steps: int = 20,
    ) -> float:
        """
        레이블된 샘플로 최적 threshold를 탐색합니다.

        Parameters
        ----------
        labeled_samples : list of (text, filler_indices)
            예: [("어 오늘 음 회의가", [0, 2]), ...]
        search_range : (min, max)
            탐색할 threshold 범위
        steps : int
            탐색 단계 수

        Returns
        -------
        best_threshold : float
        """
        lo, hi = search_range
        step = (hi - lo) / steps
        candidates = [lo + step * i for i in range(steps + 1)]

        best_f1, best_thresh = -1.0, self.threshold
        for thresh in candidates:
            self.threshold = thresh
            tp = fp = fn = 0
            for text, gold_indices in labeled_samples:
                result = self.detect(text)
                pred_set = {f.index for f in result.fillers}
                gold_set = set(gold_indices)
                tp += len(pred_set & gold_set)
                fp += len(pred_set - gold_set)
                fn += len(gold_set - pred_set)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0 else 0.0
            )
            if f1 > best_f1:
                best_f1, best_thresh = f1, thresh

        self.threshold = best_thresh
        print(
            f"[Calibrate] 최적 threshold={best_thresh:.3f}  "
            f"F1={best_f1:.4f}"
        )
        return best_thresh

    # ------------------------------------------------------------------
    # 내부 로직
    # ------------------------------------------------------------------

    def _pos_tag(self, text: str) -> list[tuple[str, str]]:
        """형태소 분석 결과 [(어절, 품사), ...] 반환."""
        if self.tagger is not None:
            try:
                return self.tagger.pos(text, norm=True, stem=False)
            except Exception as e:
                print(f"[POS] 분석 실패 ({e}) → fallback")
        # fallback: 공백 분리, 품사 UNK
        return [(t, "Unknown") for t in _fallback_tokenize(text)]

    def _dict_score(self, token: str, pos: str) -> float:
        """사전 기반 점수. 품사 조건을 만족하지 않으면 0 반환."""
        key = token.lower()

        # 반복 문자 정규화: '어어어' → '어'
        normalized = re.sub(r"(.)\1+", r"\1", key)

        for lookup in (key, normalized):
            if lookup in FILLER_DICT:
                score, allowed_pos = FILLER_DICT[lookup]
                if allowed_pos is None or pos in allowed_pos:
                    return score
        return 0.0

    def _compute_surprisals(self, tokens: list[str]) -> list[float]:
        """토큰별 surprisal 목록 반환. LM 없으면 모두 0."""
        if self.lm is None:
            return [0.0] * len(tokens)
        n = self.lm.n
        result = []
        for i, token in enumerate(tokens):
            context = tuple(tokens[max(0, i - (n - 1)): i])
            result.append(self.lm.token_surprise(token, context))
        return result

    def _context_score_normalized(
        self,
        token: str,
        tokens: list[str],
        idx: int,
        surprisals: list[float],
    ) -> float:
        """
        개선된 context_score:
        (1) Surprisal z-score: 문장 내 상대적으로 낮은 surprisal → 점수 ↑
            → 코퍼스 크기에 무관하게 동작
        (2) Removability window: 제거 후 이후 W개 토큰 확률 평균 비교
        두 점수를 평균하여 반환.
        """
        if self.lm is None:
            return 0.0

        # (1) Surprisal z-score 기반 점수
        if len(surprisals) >= 2:
            mean_s = statistics.mean(surprisals)
            std_s = statistics.stdev(surprisals) or 1e-9
            z = (surprisals[idx] - mean_s) / std_s
            # z가 낮을수록(= 상대적으로 낮은 surprisal) 점수 ↑
            # 시그모이드로 [0, 1] 변환
            low_surprise_score = 1.0 / (1.0 + math.exp(z))
        else:
            low_surprise_score = 0.5

        # (2) Removability: 이후 window 개 토큰 확률 비교
        removability = self._removability_window(tokens, idx)

        return (low_surprise_score + removability) / 2.0

    def _removability_window(self, tokens: list[str], idx: int) -> float:
        """
        idx 토큰 제거 시 이후 W개 토큰의 평균 log확률 변화를 반환.
        제거 후 확률이 높아질수록(= 더 자연스러워질수록) 1에 가까운 값.
        """
        if self.lm is None:
            return 0.0

        n = self.lm.n
        W = self.removability_window
        deltas = []

        for offset in range(1, W + 1):
            next_idx = idx + offset
            if next_idx >= len(tokens):
                break
            next_token = tokens[next_idx]

            # 제거 전 컨텍스트: idx를 포함한 (n-1)개
            ctx_with = tuple(tokens[max(0, next_idx - (n - 1)): next_idx])
            # 제거 후 컨텍스트: idx를 건너뛴 (n-1)개
            without_tokens = tokens[:idx] + tokens[idx + 1:]
            new_next_idx = next_idx - 1
            ctx_without = tuple(
                without_tokens[max(0, new_next_idx - (n - 1)): new_next_idx]
            )

            lp_with = self.lm.token_logprob(next_token, ctx_with)
            lp_without = self.lm.token_logprob(next_token, ctx_without)
            delta = lp_without - lp_with
            deltas.append(delta)

        if not deltas:
            return 0.5

        avg_delta = statistics.mean(deltas)
        # avg_delta > 0 이면 제거 후 더 자연스러움
        return 1.0 / (1.0 + 10 ** (-avg_delta))


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def _build_timestamp_map(
    word_timestamps: list[dict],
) -> dict[str, list[tuple[float, float]]]:
    """같은 단어의 모든 타임스탬프를 출현 순서대로 보관합니다."""
    ts_map: dict[str, list[tuple[float, float]]] = {}
    for entry in word_timestamps:
        word = entry.get("word", "").strip().lower()
        if word:
            ts_map.setdefault(word, []).append(
                (float(entry.get("start", 0)), float(entry.get("end", 0)))
            )
    return ts_map


import math
