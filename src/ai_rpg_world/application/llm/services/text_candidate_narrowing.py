"""新しい文に近い候補を上位 K 件に絞る (#1453)。

信念を作る前に「同じ意味の既存の信念があるか」を Jev に問う。既存の信念を
全部並べると選択肢が多すぎるので、先に文だけを見て候補を絞る。

## 文だけを見る

tags と cue を使わない。tags には tool 名や spot 番号が混ざっていて
(#1436)、環境を取り換えると前の環境の語彙で絞ることになる。ゲームの型
(``PlayerId`` など) も持ち込まない。Being パッケージ (#1463) へ移すときに
そのまま運べるようにする。

## 手法は差し替える

``ITextCandidateNarrower`` の実装として差し替える。既定は文字の 2 字組の
BM25 で、形態素解析・辞書・外部 API が要らない。言い換えと長い問い合わせ文に
弱いので、埋め込みの実装 (``embedding_narrowing``、#1454) を足して比べている。
手法と K は profile で選ぶ (design_decisions #28)。頭に載る信念の選び方 (#1414)
の 1 段目でも使う。
"""

from __future__ import annotations

import logging
import math
import os
import unicodedata
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

CHAR_BIGRAM_BM25 = "char_bigram_bm25"
QWEN3_EMBEDDING_8B_OPENROUTER = "qwen3_embedding_8b_openrouter"
RURI_V3_30M = "ruri_v3_30m"
RURI_V3_70M = "ruri_v3_70m"
RURI_V3_130M = "ruri_v3_130m"
RURI_V3_310M = "ruri_v3_310m"

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class NarrowingOutcome:
    """絞り込んだ候補と、実際に使った手法。

    ``fallback_reason`` は、選んだ手法が使えず別の手法で絞り直したときの理由。
    trace に残し、どの手法の結果が頭に載ったかを run の後から分けられるようにする。
    """

    hits: tuple[RankedCandidate, ...]
    narrower: str
    fallback_reason: str | None = None


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

    def narrow_with_outcome(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> NarrowingOutcome:
        """``narrow`` と同じ候補を、実際に使った手法の名前と一緒に返す。縮退する実装が上書きする。"""
        return NarrowingOutcome(
            hits=tuple(self.narrow(query, candidates, top_k=top_k)), narrower=self.name
        )


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


#: 埋め込みの置き値。OpenAI 互換の無認証 endpoint 向けにキー欄へ置く値で、キーではない。
_PLACEHOLDER_KEY = "EMPTY"
_OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
#: この repo では OpenRouter のキーがここに入っている。名前と実体がずれるので、使ったら警告に残す。
_FALLBACK_KEY_ENV = "OPENAI_API_KEY"
#: OpenRouter のキーの接頭辞。代わりの変数に本物の OpenAI のキーがある環境で、それを OpenRouter に送らない。
_OPENROUTER_KEY_PREFIX = "sk-or-"

#: Ruri v3 の大きさごとのモデル。どれを使うかは docs/experiments/issue_1454_embedding_comparison で比べた。
_RURI_V3_MODELS = {
    RURI_V3_30M: "cl-nagoya/ruri-v3-30m",
    RURI_V3_70M: "cl-nagoya/ruri-v3-70m",
    RURI_V3_130M: "cl-nagoya/ruri-v3-130m",
    RURI_V3_310M: "cl-nagoya/ruri-v3-310m",
}

SUPPORTED_TEXT_CANDIDATE_NARROWERS = frozenset(
    {CHAR_BIGRAM_BM25, QWEN3_EMBEDDING_8B_OPENROUTER, *_RURI_V3_MODELS}
)


def create_text_candidate_narrower(
    name: str, *, env: Mapping[str, str] | None = None
) -> ITextCandidateNarrower:
    """profile の名前から絞り込みの実装を組む。

    埋め込みの手法は、キーとモデルをここで確かめる。最初の想起まで遅らせると、
    組めないまま毎ターン縮退するか失敗し続けて run が最後まで走る。

    Args:
        name: profile に書いた手法の名前
        env: API のキーを読む環境。省略時は ``os.environ``。``.env`` は読まない

    Raises:
        ValueError: 知らない名前か、API の手法なのに使えるキーが無い
        RuntimeError: 手元の埋め込みの依存 (``embedding-local``) が入っていない
    """
    # 埋め込みの部品 (infrastructure) は組むときだけ import する。名前の一覧は設定の検証が
    # 起動前に使うので、ここで import すると依存の重い部品まで読み込み、循環もする。
    if name == CHAR_BIGRAM_BM25:
        return CharBigramBm25Narrower()
    if name == QWEN3_EMBEDDING_8B_OPENROUTER:
        return _openrouter_qwen3(os.environ if env is None else env)
    if name in _RURI_V3_MODELS:
        from ai_rpg_world.application.llm.services.embedding_narrowing import EmbeddingNarrower
        from ai_rpg_world.infrastructure.llm.ruri_embedder import RuriEmbedder

        return EmbeddingNarrower(
            name=name, embedder=RuriEmbedder(model_name=_RURI_V3_MODELS[name])
        )
    raise ValueError(
        f"unknown text candidate narrower: {name!r}. "
        f"valid: {sorted(SUPPORTED_TEXT_CANDIDATE_NARROWERS)}"
    )


def _openrouter_qwen3(env: Mapping[str, str]) -> ITextCandidateNarrower:
    from ai_rpg_world.application.llm.services.embedding_narrowing import (
        EmbeddingNarrower,
        FallbackNarrower,
    )
    from ai_rpg_world.infrastructure.llm.openrouter_embedder import OpenRouterEmbedder

    return FallbackNarrower(
        primary=EmbeddingNarrower(
            name=QWEN3_EMBEDDING_8B_OPENROUTER,
            embedder=OpenRouterEmbedder(api_key=_openrouter_key(env)),
        ),
        fallback=CharBigramBm25Narrower(),
    )


def _openrouter_key(env: Mapping[str, str]) -> str:
    named = (env.get(_OPENROUTER_KEY_ENV) or "").strip()
    if named and named != _PLACEHOLDER_KEY:
        return named
    fallback = (env.get(_FALLBACK_KEY_ENV) or "").strip()
    if fallback.startswith(_OPENROUTER_KEY_PREFIX):
        logger.warning(
            "embedding key was not in %s; using %s, which holds the OpenRouter key in this repository",
            _OPENROUTER_KEY_ENV,
            _FALLBACK_KEY_ENV,
        )
        return fallback
    raise ValueError(
        f"{QWEN3_EMBEDDING_8B_OPENROUTER} needs an OpenRouter key in {_OPENROUTER_KEY_ENV} "
        f"(or an OpenRouter key starting with {_OPENROUTER_KEY_PREFIX!r} in {_FALLBACK_KEY_ENV}); "
        f"{_PLACEHOLDER_KEY!r} is not a key"
    )


__all__ = [
    "CHAR_BIGRAM_BM25",
    "QWEN3_EMBEDDING_8B_OPENROUTER",
    "RURI_V3_130M",
    "RURI_V3_30M",
    "RURI_V3_310M",
    "RURI_V3_70M",
    "CharBigramBm25Narrower",
    "ITextCandidateNarrower",
    "NarrowingOutcome",
    "RankedCandidate",
    "SUPPORTED_TEXT_CANDIDATE_NARROWERS",
    "TextCandidate",
    "create_text_candidate_narrower",
]
