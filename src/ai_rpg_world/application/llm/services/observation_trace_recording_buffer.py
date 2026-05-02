"""Observation append 時に trace recorder を呼ぶ IObservationContextBuffer ラッパー。"""

from typing import List, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.services.observation_trace_recorder import (
    ObservationTraceRecorder,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ObservationTraceRecordingBuffer(IObservationContextBuffer):
    """既存 buffer に委譲しつつ、append 時に ObservationExperienceTrace を保存する。"""

    def __init__(
        self,
        inner: IObservationContextBuffer,
        recorder: ObservationTraceRecorder,
    ) -> None:
        if not isinstance(inner, IObservationContextBuffer):
            raise TypeError("inner must be IObservationContextBuffer")
        if not isinstance(recorder, ObservationTraceRecorder):
            raise TypeError("recorder must be ObservationTraceRecorder")
        self._inner = inner
        self._recorder = recorder

    @property
    def inner(self) -> IObservationContextBuffer:
        return self._inner

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
        self._inner.append(player_id, entry, runtime_context=runtime_context)
        self._recorder.record(player_id, entry, runtime_context=runtime_context)

    def get_observations(self, player_id: PlayerId) -> List[ObservationEntry]:
        return self._inner.get_observations(player_id)

    def drain(self, player_id: PlayerId) -> List[ObservationEntry]:
        return self._inner.drain(player_id)
