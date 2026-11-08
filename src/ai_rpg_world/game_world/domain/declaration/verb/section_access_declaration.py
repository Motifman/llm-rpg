from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import Exertion
from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.declaration.spot import SpotSectionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import DefaultDuration
from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import DisplayName, Ticks


@final
@dataclass(frozen=True)
class SectionAccessDeclaration:
    section: SpotSectionDeclaration
    enter_label: DisplayName
    leave_label: DisplayName
    enter_text: TextWithUnassignedPeople
    leave_text: TextWithUnassignedPeople
    exertion: Exertion
    duration: Ticks | DefaultDuration
    entry_condition: Condition
    perceived_as: PerceptionDeclaration
