from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, InteractionId, WorldStageId


@final
@dataclass(frozen=True)
class AllActionsAllowed:
    def __contains__(self, action: object) -> bool:
        return True


@final
@dataclass(frozen=True)
class WorldStageDeclaration:
    stage_id: WorldStageId
    name: DisplayName
    description: DescriptionText
    allowed_actions: frozenset[ActionKind | InteractionId] | AllActionsAllowed

    def allows(self, kind: ActionKind) -> bool:
        return kind in self.allowed_actions

    def allows_interaction(self, interaction: InteractionId) -> bool:
        return interaction in self.allowed_actions
