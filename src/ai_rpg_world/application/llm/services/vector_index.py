"""文のベクトルを持ち、候補の中から近い順に引く索引 (#1454)。

埋め込みで絞る部品 (``EmbeddingNarrower``) は、ベクトルの持ち方と比べ方をこの
索引に任せる。既定の ``InMemoryExactVectorIndex`` は、手元のメモリに持ち、全件を
行列積 1 回で比べる。信念は 1 人数十件なので、近似検索は要らない。エピソードの
件数で全件の比較が重くなったら、近似検索の索引 (sqlite-vec、faiss など) を
``IVectorIndex`` の実装として足す (design_decisions D1454)。

ベクトルは長さ 1 にそろえて渡す。内積がそのまま cosine になる。候補は文で渡す。
想起の候補は、その Being のその時点で有効な信念に限られるので、索引の全件ではなく
候補の中から引く。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_DEFAULT_MAX_VECTORS = 4096


class VectorDimensionMismatchError(ValueError):
    """問い合わせと入れたベクトルの次元が違う。埋め込みのモデルが途中で替わったときに起きる。"""


class IVectorIndex(ABC):
    @abstractmethod
    def missing(self, texts: Sequence[str]) -> list[str]:
        """まだ入っていない文を、重ねずに渡した順で返す。"""
        raise NotImplementedError

    @abstractmethod
    def add(self, texts: Sequence[str], vectors: NDArray[np.float32]) -> None:
        """文と、長さ 1 にそろえたベクトルの行を対にして入れる。

        Raises:
            ValueError: 文とベクトルの数が違う
        """
        raise NotImplementedError

    @abstractmethod
    def search(
        self, query: NDArray[np.float32], among: Sequence[str], *, top_k: int
    ) -> list[tuple[int, float]]:
        """``among`` の中から、``query`` と向きの近い順に (``among`` の中の位置, 点) を最大 ``top_k`` 件返す。

        点が 0 以下の候補は返さない。同点は ``among`` の順に並べる。

        Raises:
            KeyError: ``among`` に入っていない文がある
            VectorDimensionMismatchError: 次元が合わない
        """
        raise NotImplementedError


class InMemoryExactVectorIndex(IVectorIndex):
    """手元のメモリに持ち、全件を行列積で比べる。持てる数を超えたら、長く使っていない文から捨てる。"""

    def __init__(self, *, max_vectors: int = _DEFAULT_MAX_VECTORS) -> None:
        if max_vectors < 1:
            raise ValueError("max_vectors must be >= 1")
        self._max = max_vectors
        self._vectors: OrderedDict[str, NDArray[np.float32]] = OrderedDict()

    def missing(self, texts: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(t for t in texts if t not in self._vectors))

    def add(self, texts: Sequence[str], vectors: NDArray[np.float32]) -> None:
        if len(texts) != len(vectors):
            raise ValueError(f"text count {len(texts)} != vector count {len(vectors)}")
        for text, vector in zip(texts, vectors):
            self._vectors[text] = vector
            self._vectors.move_to_end(text)

    def search(
        self, query: NDArray[np.float32], among: Sequence[str], *, top_k: int
    ) -> list[tuple[int, float]]:
        if not among:
            return []
        if len(among) > self._max:
            logger.warning(
                "%d candidates exceed max_vectors=%d; their vectors are rebuilt on every search",
                len(among),
                self._max,
            )
        rows = [self._vectors[t] for t in among]
        dimensions = sorted({row.shape[0] for row in rows})
        if len(dimensions) != 1:
            raise VectorDimensionMismatchError(f"stored vectors have mixed dimensions {dimensions}")
        matrix = np.vstack(rows)
        if matrix.shape[1] != query.shape[0]:
            raise VectorDimensionMismatchError(
                f"vector dimension mismatch: query {query.shape[0]} != stored {matrix.shape[1]}"
            )
        # macOS の Accelerate では、値は正しいまま行列積が浮動小数点の警告を出す。
        # 警告は止め、値が有限かを自分で確かめる。
        with np.errstate(all="ignore"):
            scores = matrix @ query
        if not np.isfinite(scores).all():
            raise FloatingPointError("vector search produced non-finite scores")
        # stable な並べ替えで点の降順にし、同点は渡した順に残す。
        order = np.argsort(-scores, kind="stable")[:top_k]
        for text in among:
            self._vectors.move_to_end(text)
        # 捨てるのは比べたあと。add と search の間に捨てると、この検索の候補が欠ける。
        while len(self._vectors) > self._max:
            self._vectors.popitem(last=False)
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0.0]


__all__ = ["IVectorIndex", "InMemoryExactVectorIndex", "VectorDimensionMismatchError"]
