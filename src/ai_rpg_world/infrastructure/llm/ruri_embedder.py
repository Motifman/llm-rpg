"""手元の Ruri v3 (cl-nagoya/ruri-v3-*、Apache-2.0) で文をベクトルにする (#1454)。

Ruri v3 は、問い合わせ文に「検索クエリ: 」、検索される文に「検索文書: 」を付けて
学習している。付けないと検索の精度が落ちる。

sentence-transformers と PyTorch は重いので、任意の依存 ``embedding-local`` に
置く。モデルは組む時点で読む。最初の想起まで遅らせると、読めないときに想起が
毎ターン失敗したまま run が最後まで走る。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ai_rpg_world.application.llm.services.embedding_narrowing import ITextEmbedder

_QUERY_PREFIX = "検索クエリ: "
_DOCUMENT_PREFIX = "検索文書: "


class RuriEmbedder(ITextEmbedder):
    def __init__(self, *, model_name: str, model: Any | None = None) -> None:
        """``model`` は差し替え用。省略すると ``model_name`` を sentence-transformers で読む。

        Raises:
            RuntimeError: sentence-transformers が入っていない
        """
        self._model_name = model_name
        self._model = model if model is not None else _load(model_name)

    @property
    def name(self) -> str:
        return self._model_name

    def embed_queries(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._encode([_QUERY_PREFIX + t for t in texts])

    def embed_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._encode([_DOCUMENT_PREFIX + t for t in texts])

    def _encode(self, texts: list[str]) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.asarray(self._model.encode(texts), dtype=np.float32)


def _load(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            f"{model_name} needs sentence-transformers. "
            "Install the optional dependency: uv sync --extra embedding-local"
        ) from exc
    return SentenceTransformer(model_name)


__all__ = ["RuriEmbedder"]
