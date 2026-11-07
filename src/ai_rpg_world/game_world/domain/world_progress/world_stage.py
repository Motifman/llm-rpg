from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldStageId, WorldTick
from ai_rpg_world.game_world.domain.world_progress._event_stamp import new_event_stamp


@final
@dataclass(frozen=True)
class WorldStageChangedEvent(DomainEvent):
    world_id: WorldId
    before: WorldStageId
    after: WorldStageId
    at: WorldTick


class WorldStage(AggregateRoot[WorldStageChangedEvent]):
    def __init__(self, world_id: WorldId, current: WorldStageId, entered_at: WorldTick) -> None:
        super().__init__()
        self._world_id = world_id
        self._current = current
        self._entered_at = entered_at

    @classmethod
    def open(cls, world_id: WorldId, initial: WorldStageDeclaration, now: WorldTick) -> WorldStage:
        return cls(world_id, initial.stage_id, now)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def enter(self, stage: WorldStageDeclaration, now: WorldTick) -> None:
        if stage.stage_id == self._current:
            return
        before = self._current
        self._current = stage.stage_id
        self._entered_at = now
        self.add_event(
            WorldStageChangedEvent(
                **new_event_stamp(), world_id=self._world_id, before=before, after=self._current, at=now
            )
        )

    def current(self) -> WorldStageId:
        return self._current

    def entered_at(self) -> WorldTick:
        return self._entered_at
