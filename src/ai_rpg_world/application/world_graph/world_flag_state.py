from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, FrozenSet, Optional

from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry


class WorldFlagMutationSource(str, Enum):
    """world flag を変更した公開経路。trace の安定した分類値でもある。"""

    SPOT_INTERACTION = "spot_interaction"
    ITEM_INTERACTION = "item_interaction"
    PLAYER_INTERACTION = "player_interaction"
    SYNCHRONIZED_ACTION = "synchronized_action"
    SCENARIO_EVENT = "scenario_event"
    PREPARED_ACTION = "prepared_action"
    SYNCHRONIZED_PREPARE = "synchronized_prepare"
    MEETING_RESOLUTION = "meeting_resolution"
    SNAPSHOT_RESTORE = "snapshot_restore"


@dataclass(frozen=True)
class WorldFlagMutationContext:
    """状態だけからは復元できない flag 変更の因果。"""

    source: WorldFlagMutationSource
    actor_player_id: int | None


@dataclass(frozen=True)
class WorldFlagChange:
    """一つの flag が立った、または降りた状態遷移。"""

    flag_name: str
    is_set: bool
    context: WorldFlagMutationContext


class MutableWorldFlagState:
    """アプリ層で保持する可変なワールドフラグ状態（スポットグラフモード用）。

    2D タイルマップモードでは使用しない。同一セッション内のインタラクション結果を蓄積する。
    """

    def __init__(self, initial: WorldFlagRegistry | None = None) -> None:
        self._registry = initial or WorldFlagRegistry.empty()
        self._change_callback: Optional[Callable[[WorldFlagChange], None]] = None

    def as_frozen_set(self) -> FrozenSet[str]:
        return self._registry.as_frozen_set()

    def set_change_callback(
        self, callback: Optional[Callable[[WorldFlagChange], None]]
    ) -> None:
        """状態遷移の通知先を後付けする。未設定なら状態変更だけを行う。"""
        self._change_callback = callback

    def exchange_change_callback(
        self, callback: Optional[Callable[[WorldFlagChange], None]]
    ) -> Optional[Callable[[WorldFlagChange], None]]:
        """通知先を差し替え、差し替え前の通知先を返す。

        CommandScopeのrollback参加adapterがcommand中の通知を一時保留し、
        commit後だけ元の通知先へ渡すための境界である。
        """
        previous = self._change_callback
        self._change_callback = callback
        return previous

    def add(self, flag_name: str, *, context: WorldFlagMutationContext) -> None:
        """フラグを1つ追加する。"""
        before = self.as_frozen_set()
        self._registry = self._registry.with_added(flag_name)
        self._emit_changes(before, self.as_frozen_set(), context)

    def remove(self, flag_name: str, *, context: WorldFlagMutationContext) -> None:
        """フラグを1つ除去する（存在しなくても例外にしない）。"""
        before = self.as_frozen_set()
        self._registry = self._registry.with_removed(flag_name)
        self._emit_changes(before, self.as_frozen_set(), context)

    def replace_from_interaction(
        self,
        new_flags: FrozenSet[str],
        *,
        context: WorldFlagMutationContext,
    ) -> None:
        """ドメインの InteractionExecutionResult.new_flags をそのまま反映する。"""
        before = self.as_frozen_set()
        self._registry = WorldFlagRegistry.from_frozen_set(new_flags)
        self._emit_changes(before, self.as_frozen_set(), context)

    def _emit_changes(
        self,
        before: FrozenSet[str],
        after: FrozenSet[str],
        context: WorldFlagMutationContext,
    ) -> None:
        callback = self._change_callback
        if callback is None:
            return
        for flag_name in sorted(before - after):
            callback(
                WorldFlagChange(
                    flag_name=flag_name,
                    is_set=False,
                    context=context,
                )
            )
        for flag_name in sorted(after - before):
            callback(
                WorldFlagChange(
                    flag_name=flag_name,
                    is_set=True,
                    context=context,
                )
            )


__all__ = [
    "MutableWorldFlagState",
    "WorldFlagChange",
    "WorldFlagMutationContext",
    "WorldFlagMutationSource",
]
