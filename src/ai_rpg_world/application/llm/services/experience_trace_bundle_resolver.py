"""EpisodeCandidate の source_trace_id から ExperienceTrace を解決する。"""

from __future__ import annotations

from typing import Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    ObservationExperienceTrace,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    ExperienceTraceUnion,
    IActionExperienceTraceStore,
    IObservationExperienceTraceStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ExperienceTraceBundleResolver:
    """`action:{trace_id}` / `observation:{trace_id}` 形式でストアから復元する。"""

    def __init__(
        self,
        action_trace_store: IActionExperienceTraceStore,
        observation_trace_store: IObservationExperienceTraceStore,
    ) -> None:
        if not isinstance(action_trace_store, IActionExperienceTraceStore):
            raise TypeError("action_trace_store must be IActionExperienceTraceStore")
        if not isinstance(observation_trace_store, IObservationExperienceTraceStore):
            raise TypeError(
                "observation_trace_store must be IObservationExperienceTraceStore"
            )
        self._action_trace_store = action_trace_store
        self._observation_trace_store = observation_trace_store

    def resolve_ordered(
        self,
        player_id: PlayerId,
        source_trace_ids: Tuple[str, ...],
    ) -> Tuple[ExperienceTraceUnion, ...]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(source_trace_ids, tuple):
            raise TypeError("source_trace_ids must be tuple")
        out: list[ExperienceTraceUnion] = []
        for source_id in source_trace_ids:
            if not isinstance(source_id, str):
                raise TypeError("source_trace_ids must contain str")
            if source_id.startswith("action:"):
                raw_id = source_id[len("action:") :]
                trace = self._action_trace_store.find_by_trace_id(player_id, raw_id)
                if trace is None:
                    raise ValueError(f"missing action trace for {source_id!r}")
                out.append(trace)
            elif source_id.startswith("observation:"):
                raw_id = source_id[len("observation:") :]
                trace = self._observation_trace_store.find_by_trace_id(
                    player_id, raw_id
                )
                if trace is None:
                    raise ValueError(f"missing observation trace for {source_id!r}")
                out.append(trace)
            else:
                raise ValueError(
                    f"source_trace_id must start with action: or observation:, got {source_id!r}"
                )
        return tuple(out)
