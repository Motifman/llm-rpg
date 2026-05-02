"""観測コンテキストバッファのデフォルト実装（in-memory）"""

from typing import Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultObservationContextBuffer(IObservationContextBuffer):
    """プレイヤーごとに観測をリストで保持する in-memory 実装"""

    def __init__(self) -> None:
        self._buffer: Dict[int, List[ObservationEntry]] = {}

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
        if self._key(player_id) not in self._buffer:
            self._buffer[self._key(player_id)] = []
        self._buffer[self._key(player_id)].append(entry)

    def get_observations(self, player_id: PlayerId) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return list(self._buffer.get(self._key(player_id), []))

    def drain(self, player_id: PlayerId) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        key = self._key(player_id)
        entries = self._buffer.get(key, [])
        self._buffer[key] = []
        return list(entries)
