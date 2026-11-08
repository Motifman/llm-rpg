from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActorRequirement,
    DoesNotUseBody,
    Exertion,
    LivingOnly,
    UsesBody,
)
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import PassageStateDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.sound import SoundLoss
from ai_rpg_world.game_world.domain.value_object import DisplayName, InteractionId, PassageStateName
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId


@final
@dataclass(frozen=True)
class HappeningForTests:
    happening_id: HappeningId


@final
@dataclass(frozen=True)
class ReactionForTests:
    reaction_id: ReactionId


@final
@dataclass(frozen=True)
class JointActionForTests:
    joint_id: JointActionId


@final
@dataclass(frozen=True)
class InteractionForTests:
    interaction_id: InteractionId
    exertion: Exertion = field(default_factory=UsesBody)
    actor_requirement: ActorRequirement = field(default_factory=LivingOnly)
    allows_stealth: bool = False
    reaches_unseen: bool = False
    arguments: tuple[ArgumentDeclaration, ...] = ()


@final
@dataclass(frozen=True)
class SectionAccessForTests:
    section: SpotSectionDeclaration
    exertion: Exertion = field(default_factory=DoesNotUseBody)


OPEN = PassageStateName("open")


def open_passage_states() -> tuple[PassageStateDeclaration, ...]:
    return (
        PassageStateDeclaration(
            name=OPEN, display_name=DisplayName("開いている"), traversable=True, sound_loss=SoundLoss(0)
        ),
    )
