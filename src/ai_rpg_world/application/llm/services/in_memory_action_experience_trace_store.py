"""ActionExperienceTrace の in-memory 実装。"""

from typing import Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import ActionExperienceTrace
from ai_rpg_world.application.llm.contracts.interfaces import IActionExperienceTraceStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryActionExperienceTraceStore(IActionExperienceTraceStore):
    """プレイヤーごとに action trace を保持する in-memory store。"""

    def __init__(self, max_entries_per_player: int = 1000) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._store: Dict[int, List[ActionExperienceTrace]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(self, player_id: PlayerId, trace: ActionExperienceTrace) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(trace, ActionExperienceTrace):
            raise TypeError("trace must be ActionExperienceTrace")
        if trace.agent_id != player_id.value:
            raise ValueError("trace.agent_id must match player_id")
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(trace)
        if len(self._store[key]) > self._max_entries:
            self._store[key] = self._store[key][-self._max_entries :]

    def get_recent(
        self, player_id: PlayerId, limit: int
    ) -> List[ActionExperienceTrace]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if limit == 0:
            return []
        key = self._key(player_id)
        entries = self._store.get(key, [])
        sorted_entries = sorted(entries, key=lambda e: e.occurred_at, reverse=True)
        return sorted_entries[:limit]

    def find_by_trace_id(
        self, player_id: PlayerId, trace_id: str
    ) -> Optional[ActionExperienceTrace]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(trace_id, str):
            raise TypeError("trace_id must be str")
        key = self._key(player_id)
        for trace in self._store.get(key, []):
            if trace.trace_id == trace_id:
                return trace
        return None
