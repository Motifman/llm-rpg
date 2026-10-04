"""新しい文に近い候補を上位 K 件に絞る (#1453)。

信念を作る前に「同じ意味の既存の信念があるか」を Jev に問う。既存の信念を
全部並べると選択肢が多すぎるので、先に文だけを見て候補を絞る。

## 文だけを見る

tags と cue を使わない。tags には tool 名や spot 番号が混ざっていて
(#1436)、環境を取り換えると前の環境の語彙で絞ることになる。ゲームの型
(``PlayerId`` など) も持ち込まない。Being パッケージ (#1463) へ移すときに
そのまま運べるようにする。

## 手法は差し替える

``ITextCandidateNarrower`` の実装として差し替える。最初の実装は文字の 2 字組の
BM25 で、形態素解析・辞書・外部 API が要らない。言い換えに弱いので、相方を
取りこぼす割合が高ければ埋め込みの実装を足す。手法と K は profile で選ぶ
(design_decisions #28)。頭に載る信念の選び方 (#1414) の 1 段目でも使う。
"""

from __future__ import annotations

import math
import unicodedata
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

CHAR_BIGRAM_BM25 = "char_bigram_bm25"


@dataclass(frozen=True)
class TextCandidate:
    """絞り込みの候補。``key`` は呼び出し側が候補を引き当てるためだけに使う。"""

    key: str
    text: str


@dataclass(frozen=True)
class RankedCandidate:
    """絞り込んだ候補。``score`` の尺度は手法ごとに違い、手法をまたいで比べない。"""

    key: str
    text: str
    score: float


class ITextCandidateNarrower(ABC):
    """新しい文と候補の一覧を受け、近い順に上位 K 件を返す。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """profile で選ぶときの名前。trace にも残す。"""
        raise NotImplementedError

    @abstractmethod
    def narrow(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> tuple[RankedCandidate, ...]:
        """近い順に最大 ``top_k`` 件を返す。近いと言えない候補は返さない。

        Raises:
            ValueError: ``top_k`` が 1 未満
        """
        raise NotImplementedError


class CharBigramBm25Narrower(ITextCandidateNarrower):
    """文字の 2 字組を語とみなした BM25。IDF は渡された候補の集合で数える。"""

    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 < 0:
            raise ValueError("k1 must be >= 0")
        if not 0.0 <= b <= 1.0:
            raise ValueError("b must be in [0, 1]")
        self._k1 = k1
        self._b = b

    @property
    def name(self) -> str:
        return CHAR_BIGRAM_BM25

    def narrow(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> tuple[RankedCandidate, ...]:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        query_terms = set(_char_bigrams(query))
        if not candidates or not query_terms:
            return ()
        documents = [Counter(_char_bigrams(c.text)) for c in candidates]
        lengths = [sum(d.values()) for d in documents]
        average_length = sum(lengths) / len(lengths) or 1.0
        document_frequency: Counter[str] = Counter()
        for document in documents:
            document_frequency.update(document.keys())
        count = len(documents)

        scored: list[tuple[float, int]] = []
        for index, (document, length) in enumerate(zip(documents, lengths)):
            score = 0.0
            for term in query_terms:
                frequency = document.get(term, 0)
                if not frequency:
                    continue
                n = document_frequency[term]
                # 全候補に現れる語でも負にならない形 (Lucene と同じ)。
                idf = math.log((count - n + 0.5) / (n + 0.5) + 1.0)
                norm = self._k1 * (1.0 - self._b + self._b * length / average_length)
                score += idf * frequency * (self._k1 + 1.0) / (frequency + norm)
            if score > 0.0:
                scored.append((score, index))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return tuple(
            RankedCandidate(candidates[i].key, candidates[i].text, score)
            for score, i in scored[:top_k]
        )


def _char_bigrams(text: str) -> list[str]:
    """改行・句読点・空白・記号を区切りにして、区切りの中だけで 2 字組を作る。

    区切りを消してからつなぐと、別々の文の境目に「屋ノ」(「廃屋」と「ノア」) のような
    無い言葉が生まれる (#1414)。区切りで 1 文字だけ残った断片は、ほかに 2 字組が無い
    ときだけ、その文字で比べる。
    """
    pieces: list[str] = []
    current: list[str] = []
    for ch in unicodedata.normalize("NFKC", text).lower():
        if unicodedata.category(ch).startswith(("P", "Z", "C", "S")):
            if current:
                pieces.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        pieces.append("".join(current))
    bigrams = [piece[i : i + 2] for piece in pieces for i in range(len(piece) - 1)]
    return bigrams or pieces


_NARROWERS = {CHAR_BIGRAM_BM25: CharBigramBm25Narrower}

SUPPORTED_TEXT_CANDIDATE_NARROWERS = frozenset(_NARROWERS)


def create_text_candidate_narrower(name: str) -> ITextCandidateNarrower:
    """profile の名前から絞り込みの実装を組む。

    Raises:
        ValueError: 知らない名前
    """
    factory = _NARROWERS.get(name)
    if factory is None:
        raise ValueError(
            f"unknown text candidate narrower: {name!r}. "
            f"valid: {sorted(SUPPORTED_TEXT_CANDIDATE_NARROWERS)}"
        )
    return factory()


__all__ = [
    "CHAR_BIGRAM_BM25",
    "CharBigramBm25Narrower",
    "ITextCandidateNarrower",
    "RankedCandidate",
    "SUPPORTED_TEXT_CANDIDATE_NARROWERS",
    "TextCandidate",
    "create_text_candidate_narrower",
]
