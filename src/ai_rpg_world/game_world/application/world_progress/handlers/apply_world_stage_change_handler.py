from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.world_progress.apply_world_stage_change import (
    ApplyWorldStageChange,
    ApplyWorldStageChangeCommand,
)
from ai_rpg_world.game_world.domain.world_progress import WorldStageChangedEvent


@final
class ApplyWorldStageChangeHandler(EventHandler[WorldStageChangedEvent]):
    def __init__(self, apply_world_stage_change: ApplyWorldStageChange) -> None:
        self._apply_world_stage_change = apply_world_stage_change

    def handle(self, event: WorldStageChangedEvent) -> None:
        self._apply_world_stage_change(ApplyWorldStageChangeCommand(before=event.before, after=event.after, at=event.at))
