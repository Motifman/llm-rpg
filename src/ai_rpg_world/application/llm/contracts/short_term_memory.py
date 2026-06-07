"""短期記憶 (Phase 2) の値型。

- ``L4MidSummary``: rolling summary の中期帯 (15 raw 観測 → 1 件) 1 世代分。
- ``IShortTermMemorySummaryCompletionPort``: LLM 完了 port。

詳細: docs/memory_system/short_term_memory_design.md §3, §4。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Tuple


@dataclass(frozen=True)
class L4MidSummary:
    """中期帯 (L4) 1 世代分の主観要約。

    Phase 2 (#356 後続): sliding window が 15 raw 件を超えたタイミングで
    LLM で生成される。3 世代まで保持して prompt §「【最近の流れ】」に出す。

    schema 設計指針 (docs §4.1):
    - **学び / 関係性 / 世界ルール は含めない** (semantic 経路の責務)
    - **narrative continuity** に絞る (流れ + 気分 + 未解決)
    - **永続名のみ** (P1 等のターン局所ラベルを焼かない)
    """

    summary_id: str
    player_id: int
    raw_count: int
    generated_at: datetime
    compressed_activity: str
    emotional_summary: str
    unresolved: Tuple[str, ...] = ()
    # template fallback で生成された (= LLM 抽象化が走らなかった) かを表すフラグ。
    # trace / 分析で「LLM 成功率」を出すのに使う。default False。
    is_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.summary_id, str) or not self.summary_id.strip():
            raise ValueError("summary_id must be non-empty str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.raw_count, int) or self.raw_count < 0:
            raise ValueError("raw_count must be non-negative int")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be datetime")
        if not isinstance(self.compressed_activity, str):
            raise TypeError("compressed_activity must be str")
        if not isinstance(self.emotional_summary, str):
            raise TypeError("emotional_summary must be str")
        if not isinstance(self.unresolved, tuple):
            raise TypeError("unresolved must be tuple[str, ...]")
        for i, item in enumerate(self.unresolved):
            if not isinstance(item, str):
                raise TypeError(f"unresolved[{i}] must be str")
        if not isinstance(self.is_fallback, bool):
            raise TypeError("is_fallback must be bool")


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


@dataclass(frozen=True)
class L5LongSummary:
    """長期帯 (L5) 1 件分の自己像と世界観 (Phase 3)。

    L4 が ``keep_gen + 1`` 世代目に達したとき、最古 L4 + 現在の L5 を LLM で
    統合して新世代 L5 が生成される。L5 は **1 player につき 1 件のみ** 保持。

    schema 設計指針 (docs §4.2):
    - **narrative voice のみ**: 学び / 関係性 / 世界ルールは semantic 経路の責務
    - **時系列の細部は捨てる**: L5 は時を超えた「いまの自分」「いまの世界観」
    - **persona drift 防止**: 性格 (persona) は previous_l5 のものを保ち、
      事実認識のみ更新される。プロンプト側で強制
    """

    summary_id: str
    player_id: int
    generation_index: int  # 何回目の L5 か (drift 検出用)
    generated_at: datetime
    self_image: str
    world_view: str
    is_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.summary_id, str) or not self.summary_id.strip():
            raise ValueError("summary_id must be non-empty str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.generation_index, int) or self.generation_index < 0:
            raise ValueError("generation_index must be non-negative int")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be datetime")
        if not isinstance(self.self_image, str):
            raise TypeError("self_image must be str")
        if not isinstance(self.world_view, str):
            raise TypeError("world_view must be str")
        if not isinstance(self.is_fallback, bool):
            raise TypeError("is_fallback must be bool")


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
    "L4MidSummary",
    "L5LongSummary",
]
