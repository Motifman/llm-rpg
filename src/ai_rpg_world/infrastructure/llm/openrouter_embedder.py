"""OpenRouter の埋め込み API で文をベクトルにする (#1454)。

既定のモデルは ``qwen/qwen3-embedding-8b`` (100 万トークンあたり $0.01)。
Qwen3-Embedding は、問い合わせ文にだけ ``Instruct: <課題>\\nQuery:`` の指示文を
付け、検索される文はそのまま渡す決まり。指示文は英語で書く (モデルの説明が
英語の指示文で学習したとしているため)。

失敗 (通信、状態コード、応答の形) はすべて ``EmbeddingUnavailableError`` にする。
呼び出し側が 2 字組へ縮退する。キーは文面に出さない。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

from ai_rpg_world.application.llm.services.embedding_narrowing import (
    EmbeddingUnavailableError,
    ITextEmbedder,
)

DEFAULT_OPENROUTER_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_QUERY_INSTRUCTION = (
    "Given an agent's description of its current situation, retrieve the agent's own "
    "beliefs that help it decide what to do next"
)
_ENDPOINT = "https://openrouter.ai/api/v1/embeddings"
_DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass
class EmbeddingUsage:
    requests: int = 0
    failures: int = 0
    prompt_tokens: int = 0
    cost: float = 0.0


class OpenRouterEmbedder(ITextEmbedder):
    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_OPENROUTER_EMBEDDING_MODEL,
        query_instruction: str = DEFAULT_QUERY_INSTRUCTION,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._model = model
        self._instruction = query_instruction
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self.usage = EmbeddingUsage()

    @property
    def name(self) -> str:
        return f"openrouter:{self._model}"

    def embed_queries(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._embed([f"Instruct: {self._instruction}\nQuery:{t}" for t in texts])

    def embed_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._embed(list(texts))

    def _embed(self, texts: list[str]) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        self.usage.requests += 1
        try:
            return self._request(texts)
        except EmbeddingUnavailableError:
            self.usage.failures += 1
            raise

    def _request(self, texts: list[str]) -> NDArray[np.float32]:
        try:
            response = self._client.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailableError(f"{type(exc).__name__}: {exc}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingUnavailableError(
                f"HTTP {response.status_code}: body is not JSON"
            ) from exc
        if response.status_code != 200 or not isinstance(body, dict) or "data" not in body:
            raise EmbeddingUnavailableError(
                f"HTTP {response.status_code}: {_error_message(body)}"
            )
        vectors = _vectors(body["data"], expected=len(texts))
        self._count(body.get("usage"))
        return vectors

    def _count(self, usage: Any) -> None:
        """使用量は試算の記録のためだけにある。読めなくても、取れたベクトルは捨てない。"""
        if not isinstance(usage, dict):
            return
        try:
            tokens = int(usage.get("prompt_tokens") or 0)
            cost = float(usage.get("cost") or 0.0)
        except (TypeError, ValueError):
            return
        self.usage.prompt_tokens += tokens
        self.usage.cost += cost


def _error_message(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return str(body["error"].get("message") or body["error"])
    return "response has no data"


def _vectors(data: Any, *, expected: int) -> NDArray[np.float32]:
    """応答の data を、渡した文の順の行列にする。数・番号・値の誤りは縮退できる失敗にする。"""
    if not isinstance(data, list) or len(data) != expected:
        count = len(data) if isinstance(data, list) else 0
        raise EmbeddingUnavailableError(f"got {count} vectors for {expected} texts")
    try:
        by_index = {int(item["index"]): item["embedding"] for item in data}
        if sorted(by_index) != list(range(expected)):
            raise EmbeddingUnavailableError(f"embedding indexes are {sorted(by_index)}")
        matrix = np.asarray([by_index[i] for i in range(expected)], dtype=np.float32)
    except (KeyError, TypeError, ValueError) as exc:
        raise EmbeddingUnavailableError(f"malformed embedding item: {exc}") from exc
    if matrix.ndim != 2 or matrix.shape[1] == 0 or not np.isfinite(matrix).all():
        raise EmbeddingUnavailableError(f"embeddings are malformed (shape {matrix.shape})")
    return matrix


__all__ = [
    "DEFAULT_OPENROUTER_EMBEDDING_MODEL",
    "DEFAULT_QUERY_INSTRUCTION",
    "EmbeddingUsage",
    "OpenRouterEmbedder",
]
