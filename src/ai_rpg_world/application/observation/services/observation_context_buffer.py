"""観測コンテキストバッファのデフォルト実装（in-memory）"""

from typing import List, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultObservationContextBuffer(IObservationContextBuffer):
    """プレイヤーごとに観測をリストで保持する in-memory 実装"""

    def __init__(self, *, event_store: UnifiedRecentEventStore | None = None) -> None:
        self._event_store = event_store or UnifiedRecentEventStore()

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(
        self,
        player_id: PlayerId,
        entry: ObservationEntry,
        *,
        runtime_context: Optional[ToolRuntimeContextDto] = None,
    ) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        if runtime_context is not None and not isinstance(
            runtime_context, ToolRuntimeContextDto
        ):
            raise TypeError("runtime_context must be ToolRuntimeContextDto or None")
        self._event_store.append_pending_observation(player_id, entry)

    def get_observations(self, player_id: PlayerId) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._event_store.get_pending_observations(player_id)

    def drain(self, player_id: PlayerId) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._event_store.drain_pending_observations(player_id)
