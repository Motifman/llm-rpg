"""観測バッファの drain と短期記憶への追記を同期する。"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import IShortTermMemory
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def drain_observation_buffer_into_short_term_memory(
    observation_buffer: IObservationContextBuffer,
    short_term_memory: IShortTermMemory,
    player_id: PlayerId,
) -> List[ObservationEntry]:
    """
    DefaultPromptBuilder.build と同順序で、バッファを drain し短期記憶へ追記する。

    Returns:
        append_all が返す溢れ観測（短期記憶から落ちた古いもの）。drain が空なら []。
    """
    if not isinstance(observation_buffer, IObservationContextBuffer):
        raise TypeError("observation_buffer must be IObservationContextBuffer")
    if not isinstance(short_term_memory, IShortTermMemory):
        raise TypeError("short_term_memory must be IShortTermMemory")
    if not isinstance(player_id, PlayerId):
        raise TypeError("player_id must be PlayerId")

    drained = observation_buffer.drain(player_id)
    if not drained:
        return []
    return short_term_memory.append_all(player_id, drained)
