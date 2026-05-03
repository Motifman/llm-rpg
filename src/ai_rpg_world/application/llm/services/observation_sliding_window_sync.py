"""観測バッファの drain とスライディングウィンドウ append の同期（アプリケーション協調）。"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import ISlidingWindowMemory
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def drain_observation_buffer_into_sliding_window(
    observation_buffer: IObservationContextBuffer,
    sliding_window_memory: ISlidingWindowMemory,
    player_id: PlayerId,
) -> List[ObservationEntry]:
    """
    DefaultPromptBuilder.build と同順序で、バッファを drain しウィンドウへ追記する。

    Returns:
        append_all が返す溢れ観測（ウィンドウから落ちた古いもの）。drain が空なら []。
    """
    if not isinstance(observation_buffer, IObservationContextBuffer):
        raise TypeError("observation_buffer must be IObservationContextBuffer")
    if not isinstance(sliding_window_memory, ISlidingWindowMemory):
        raise TypeError("sliding_window_memory must be ISlidingWindowMemory")
    if not isinstance(player_id, PlayerId):
        raise TypeError("player_id must be PlayerId")

    drained = observation_buffer.drain(player_id)
    if not drained:
        return []
    return sliding_window_memory.append_all(player_id, drained)
