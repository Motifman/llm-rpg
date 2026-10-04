"""文の埋め込みで候補を絞る (#1454)。

2 字組の BM25 は、長い問い合わせ文の中の数語 (体の危険の語など) を拾えない
(design_decisions D1498)。埋め込みは文全体の意味を 1 本のベクトルにするので、
語の重なりが少なくても意味の近い候補を上に並べられる。

## 埋め込みを作る部品は差し替える

``ITextEmbedder`` の実装として、API (OpenRouter) と手元のモデル (Ruri v3) を
差し替える。問い合わせ文と検索される文を別の役割として渡す。モデルによって、
役割ごとに付ける接頭辞や指示文が違うため。

## ベクトルの持ち方と比べ方は索引に任せる

ベクトルは受け取った時点で長さ 1 にそろえ、索引 (``IVectorIndex``) に入れる。
既定の索引は手元のメモリで全件を行列積で比べる。件数が増えたら近似検索の索引に
差し替える (``vector_index``、design_decisions D1454)。

## 検索される側のベクトルは使い回す

信念の文は想起のたびにほとんど変わらない。ベクトルは文をキーに持ち、前に
見た文は作り直さない。文だけで決まる値なので、Being ごとには分けない。
snapshot にも載せない。読み込み直後の最初の想起で作り直す費用は、信念が
1 人 30 件ほどなら API で数百〜千トークン ($0.00001 ほど) で済む (design_decisions D1454)。

## 埋め込みを得られないとき

API の失敗は ``EmbeddingUnavailableError`` で表し、``FallbackNarrower`` が
2 字組で絞り直す。縮退先を cue の完全一致にしない (#1454)。縮退したことは
``NarrowingOutcome.fallback_reason`` で返し、呼び出し側が trace に残す。
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    ITextCandidateNarrower,
    NarrowingOutcome,
    RankedCandidate,
    TextCandidate,
)
from ai_rpg_world.application.llm.services.vector_index import (
    InMemoryExactVectorIndex,
    IVectorIndex,
    VectorDimensionMismatchError,
)

logger = logging.getLogger(__name__)

#: ベクトルを作っている間に別の想起が候補を捨てたときに、作り直す回数の上限。
_MAX_ATTEMPTS = 3
#: trace に残す縮退の理由の長さ。provider が長いエラーページを返しても trace を膨らませない。
_MAX_REASON_CHARS = 300

class EmbeddingUnavailableError(Exception):
    """埋め込みを得られなかった。通信の失敗、応答の形の誤り、数や次元の食い違い。"""


class ITextEmbedder(ABC):
    """文をベクトルにする。返すのは文の数 × 次元の 2 次元の配列で、行の順は渡した文と同じ。"""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def embed_queries(self, texts: Sequence[str]) -> ArrayLike:
        """問い合わせ文をベクトルにする。

        Raises:
            EmbeddingUnavailableError: 埋め込みを得られなかった
        """
        raise NotImplementedError

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> ArrayLike:
        """検索される文をベクトルにする。

        Raises:
            EmbeddingUnavailableError: 埋め込みを得られなかった
        """
        raise NotImplementedError


class EmbeddingNarrower(ITextCandidateNarrower):
    """問い合わせ文と候補の文の cosine 類似度で並べる。0 以下の候補は返さない。

    ベクトルの持ち方と比べ方は ``index`` に任せる。省略すると手元のメモリで全件を比べる。
    """

    def __init__(
        self,
        *,
        name: str,
        embedder: ITextEmbedder,
        index: IVectorIndex | None = None,
    ) -> None:
        if not isinstance(embedder, ITextEmbedder):
            raise TypeError("embedder must be ITextEmbedder")
        self._name = name
        self._embedder = embedder
        self._index = index if index is not None else InMemoryExactVectorIndex()
        # 1 ターンの中で、複数の人の想起が並列に同じ索引を使う。
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def embedder(self) -> ITextEmbedder:
        return self._embedder

    def narrow(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> tuple[RankedCandidate, ...]:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if not candidates or not query:
            return ()
        query_vector = self._unit_rows(self._embedder.embed_queries([query]), expected=1)[0]
        if not query_vector.any():
            raise EmbeddingUnavailableError(f"{self._embedder.name} returned a zero-length query vector")
        texts = [c.text for c in candidates]
        for _ in range(_MAX_ATTEMPTS):
            with self._lock:
                missing = self._index.missing(texts)
            # ベクトルを作る (API を呼ぶ) 間は鍵を持たない。並列の想起を待たせない。
            fresh = self._document_rows(missing, dimension=query_vector.shape[0]) if missing else None
            with self._lock:
                if missing and fresh is not None:
                    self._index.add(missing, fresh)
                # ベクトルを作っている間に、別の想起が索引から捨てた文があれば作り直す。
                if self._index.missing(texts):
                    continue
                try:
                    hits = self._index.search(query_vector, texts, top_k=top_k)
                except (VectorDimensionMismatchError, FloatingPointError) as exc:
                    raise EmbeddingUnavailableError(f"{type(exc).__name__}: {exc}") from exc
            return tuple(
                RankedCandidate(candidates[i].key, candidates[i].text, score) for i, score in hits
            )
        raise EmbeddingUnavailableError(
            f"candidate vectors were evicted by concurrent recalls {_MAX_ATTEMPTS} times"
        )

    def _document_rows(self, texts: list[str], *, dimension: int) -> NDArray[np.float32]:
        rows = self._unit_rows(self._embedder.embed_documents(texts), expected=len(texts))
        # 次元の合わないベクトルは索引に入れない。入れると次の想起も同じ失敗を続ける。
        if rows.shape[1] != dimension:
            raise EmbeddingUnavailableError(
                f"vector dimension mismatch: query {dimension} != candidates {rows.shape[1]}"
            )
        return rows

    def _unit_rows(self, raw: ArrayLike, *, expected: int) -> NDArray[np.float32]:
        """埋め込みの部品の返した値を確かめ、長さ 1 にそろえる。形や値の誤りは縮退できる失敗にする。"""
        try:
            array = np.asarray(raw, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise EmbeddingUnavailableError(f"{self._embedder.name} returned non-numeric vectors: {exc}") from exc
        if array.ndim != 2 or array.shape[0] != expected or array.shape[1] == 0:
            raise EmbeddingUnavailableError(
                f"{self._embedder.name} returned vectors of shape {array.shape} for {expected} texts"
            )
        if not np.isfinite(array).all():
            raise EmbeddingUnavailableError(f"{self._embedder.name} returned non-finite vectors")
        # 長さは float64 で測る。float32 のままだと大きな値で長さが inf になり、ベクトルが 0 に潰れる。
        wide = array.astype(np.float64)
        norms = np.linalg.norm(wide, axis=1, keepdims=True)
        # 長さ 0 のベクトルはどの向きにも近くないので、0 のまま残し点を 0 にする。
        unit: NDArray[np.float32] = np.divide(
            wide, norms, out=np.zeros_like(wide), where=norms > 0
        ).astype(np.float32)
        return unit


class FallbackNarrower(ITextCandidateNarrower):
    """``primary`` が埋め込みを得られなければ ``fallback`` で絞り直し、理由を返す。"""

    def __init__(
        self, *, primary: ITextCandidateNarrower, fallback: ITextCandidateNarrower
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return self._primary.name

    @property
    def primary(self) -> ITextCandidateNarrower:
        return self._primary

    def narrow(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> tuple[RankedCandidate, ...]:
        return self.narrow_with_outcome(query, candidates, top_k=top_k).hits

    def narrow_with_outcome(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> NarrowingOutcome:
        try:
            hits = self._primary.narrow(query, candidates, top_k=top_k)
        except EmbeddingUnavailableError as exc:
            reason = f"{type(exc).__name__}: {exc}"[:_MAX_REASON_CHARS]
            logger.warning(
                "narrower %s fell back to %s: %s", self._primary.name, self._fallback.name, reason
            )
            return NarrowingOutcome(
                hits=tuple(self._fallback.narrow(query, candidates, top_k=top_k)),
                narrower=self._fallback.name,
                fallback_reason=reason,
            )
        return NarrowingOutcome(hits=tuple(hits), narrower=self._primary.name)


__all__ = [
    "EmbeddingNarrower",
    "EmbeddingUnavailableError",
    "FallbackNarrower",
    "ITextEmbedder",
]
