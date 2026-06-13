"""短期記憶 (Phase 2) の LLM 完了 Port。

DDD 再編 (Issue #470 Phase 1):
- 旧: 本ファイルに L4MidSummary / L5LongSummary (Value Object) と
  Port (LLM 完了 interface) が同居していた
- 新: Value Object は ``domain/memory/short_term/value_object/`` に昇格、
  Port は application 層の責務 (= 外部 LLM API への口) として本ファイルに残る

L4MidSummary / L5LongSummary を使うコードは
``ai_rpg_world.domain.memory.short_term.value_object`` から import すること。

詳細: docs/memory_system/short_term_memory_design.md §3, §4。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IShortTermMemorySummaryCompletionPort(ABC):
    """L4 mid summary 生成用の無ツール JSON 完了 port。"""

    @abstractmethod
    def complete_short_term_summary_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """messages を LLM へ送り、応答文字列を JSON にパースして dict で返す。

        Raises:
            LlmApiCallException: API 失敗 / 空応答 / JSON パース不能時。
                呼び出し元 (``ShortTermMemorySummaryService``) は template
                fallback に縮退する。
        """
        raise NotImplementedError


class IShortTermMemoryLongSummaryCompletionPort(ABC):
    """L5 long summary 生成用の無ツール JSON 完了 port (Phase 3)。"""

    @abstractmethod
    def complete_short_term_long_summary_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """messages を LLM へ送り、応答文字列を JSON にパースして dict で返す。

        Raises:
            LlmApiCallException: API 失敗 / 空応答 / JSON パース不能時。
                呼び出し元 (``ShortTermMemoryLongSummaryService``) は template
                fallback に縮退する。
        """
        raise NotImplementedError


__all__ = [
    "IShortTermMemoryLongSummaryCompletionPort",
    "IShortTermMemorySummaryCompletionPort",
]
