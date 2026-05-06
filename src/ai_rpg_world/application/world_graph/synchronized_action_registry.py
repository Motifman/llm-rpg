"""同期アクショングループの prepare 状態追跡（猶予窓 + tick メタ付き）。

協力ギミック #13 で使う prepare の管理。各 prepare に tick を記録し、
SynchronizedActionResolverStageService が窓判定する。

flag format: ``sync_prep:{action_id}:{player_id}:{tick}``

既存の `PreparedActionRegistry`（PREPARED_ACTION 条件で参照される flag
形式: ``prepared:{action_id}:{player_id}``）とは別系統で運用する。
sync group に属する action_id を prepare するときは両方に記録される
（後方互換のため）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState


_FLAG_PREFIX = "sync_prep:"


@dataclass(frozen=True)
class SyncPrepareEntry:
    """1 件の sync prepare 記録。"""

    action_id: str
    player_id: int
    prepare_tick: int

    @property
    def flag(self) -> str:
        return f"{_FLAG_PREFIX}{self.action_id}:{self.player_id}:{self.prepare_tick}"


class SynchronizedActionRegistry:
    """sync group 用 prepare レジストリ。

    `prepare` で世界フラグに記録、`entries_for` で action_id に紐付く
    prepare を全列挙、`clear_entries` で指定 entries の flag を削除する。
    """

    def __init__(self, world_flag_state: MutableWorldFlagState) -> None:
        self._world_flag_state = world_flag_state

    def prepare(
        self, *, action_id: str, player_id: int, current_tick: int,
    ) -> SyncPrepareEntry:
        """sync prepare を記録する。

        同じ player が同じ action_id を再 prepare する場合、新しい
        tick で上書き（古い flag を消してから新規追加）。
        """
        if not action_id.strip():
            raise ValueError("action_id cannot be empty")
        if ":" in action_id:
            raise ValueError("action_id must not contain ':'")
        # 同 player + 同 action の旧 flag を削除
        old_flags = [
            f for f in self._world_flag_state.as_frozen_set()
            if f.startswith(f"{_FLAG_PREFIX}{action_id}:{player_id}:")
        ]
        for f in old_flags:
            self._world_flag_state.remove(f)
        entry = SyncPrepareEntry(
            action_id=action_id, player_id=player_id, prepare_tick=current_tick,
        )
        self._world_flag_state.add(entry.flag)
        return entry

    def entries_for(self, action_id: str) -> List[SyncPrepareEntry]:
        """指定 action_id に対する全 prepare を返す。"""
        prefix = f"{_FLAG_PREFIX}{action_id}:"
        out: List[SyncPrepareEntry] = []
        for f in self._world_flag_state.as_frozen_set():
            if not f.startswith(prefix):
                continue
            # parse: sync_prep:{action_id}:{player_id}:{tick}
            tail = f[len(_FLAG_PREFIX):]
            parts = tail.split(":")
            if len(parts) != 3:
                continue
            parsed_action, player_str, tick_str = parts
            if parsed_action != action_id:
                continue
            try:
                out.append(SyncPrepareEntry(
                    action_id=action_id,
                    player_id=int(player_str),
                    prepare_tick=int(tick_str),
                ))
            except ValueError:
                continue
        return out

    def clear_entries(self, entries: List[SyncPrepareEntry]) -> None:
        """指定 entries の flag を削除する。"""
        for e in entries:
            self._world_flag_state.remove(e.flag)

    def all_entries(self) -> List[SyncPrepareEntry]:
        """登録されている全 sync prepare を返す（resolver でのスキャン用）。"""
        out: List[SyncPrepareEntry] = []
        for f in self._world_flag_state.as_frozen_set():
            if not f.startswith(_FLAG_PREFIX):
                continue
            tail = f[len(_FLAG_PREFIX):]
            parts = tail.split(":")
            if len(parts) != 3:
                continue
            try:
                out.append(SyncPrepareEntry(
                    action_id=parts[0],
                    player_id=int(parts[1]),
                    prepare_tick=int(parts[2]),
                ))
            except ValueError:
                continue
        return out

    def find_oldest_for_action(self, action_id: str) -> Optional[SyncPrepareEntry]:
        """指定 action_id の最も古い prepare を返す。"""
        entries = self.entries_for(action_id)
        if not entries:
            return None
        return min(entries, key=lambda e: e.prepare_tick)
