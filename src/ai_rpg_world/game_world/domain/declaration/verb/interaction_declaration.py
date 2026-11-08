from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import ActorRequirement, Exertion
from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.shown_to_actor import ShownToActor
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import DisplayName, InteractionId, Ticks


@final
@dataclass(frozen=True)
class DefaultDuration:
    pass


@final
@dataclass(frozen=True, kw_only=True)
class InteractionDeclaration:
    interaction_id: InteractionId
    display_label: DisplayName
    precondition: Condition
    effect: Effect
    success_text: TextWithUnassignedPeople
    shows_on_success: tuple[ShownToActor, ...]
    exertion: Exertion
    actor_requirement: ActorRequirement
    perceived_as: PerceptionDeclaration
    reaches_unseen: bool
    duration: Ticks | DefaultDuration = field(default_factory=DefaultDuration)
    allows_stealth: bool
