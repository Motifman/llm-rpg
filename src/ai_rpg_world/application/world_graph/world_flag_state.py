from __future__ import annotations

from typing import FrozenSet

from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry


class MutableWorldFlagState:
    """アプリ層で保持する可変なワールドフラグ状態（スポットグラフモード用）。

    2D タイルマップモードでは使用しない。同一セッション内のインタラクション結果を蓄積する。
    """

    def __init__(self, initial: WorldFlagRegistry | None = None) -> None:
        self._registry = initial or WorldFlagRegistry.empty()

    def as_frozen_set(self) -> FrozenSet[str]:
        return self._registry.as_frozen_set()

    def replace_from_interaction(self, new_flags: FrozenSet[str]) -> None:
        """ドメインの InteractionExecutionResult.new_flags をそのまま反映する。"""
        self._registry = WorldFlagRegistry.from_frozen_set(new_flags)
