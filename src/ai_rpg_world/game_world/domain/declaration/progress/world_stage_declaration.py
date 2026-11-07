from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, InteractionId, WorldStageId


@final
@dataclass(frozen=True)
class AllActionsAllowed:
    pass


@final
@dataclass(frozen=True)
class WorldStageDeclaration:
    stage_id: WorldStageId
    name: DisplayName
    description: DescriptionText
    allowed_actions: frozenset[ActionKind | InteractionId] | AllActionsAllowed
