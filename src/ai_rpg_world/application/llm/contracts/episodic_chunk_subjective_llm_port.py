"""チャンクエピソードの主観フィールド（interpreted / recall_text）のみを JSON で返す LLM 完了ポート。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IEpisodicChunkSubjectiveCompletionPort(ABC):
    """interpreted と recall_text 用の無ツール chat completion（JSON object）。"""

    @abstractmethod
    def complete_episode_subjective_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        messages を LiteLLM 等へ送り、モデル応答文字列を JSON にパースして dict で返す。

        Raises:
            LlmApiCallException: API 失敗・空応答・JSON パース不能時。
        """
        raise NotImplementedError


__all__ = ["IEpisodicChunkSubjectiveCompletionPort"]
