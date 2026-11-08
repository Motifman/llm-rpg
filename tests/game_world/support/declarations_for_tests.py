from __future__ import annotations

from dataclasses import dataclass
from typing import final

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
