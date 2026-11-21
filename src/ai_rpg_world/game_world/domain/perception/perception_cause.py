from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId


@final
@dataclass(frozen=True)
class ActionTaken:
    actor: PersonId
    kind: ActionKind


@final
@dataclass(frozen=True)
class ActionFailed:
    actor: PersonId
    kind: ActionKind


@final
@dataclass(frozen=True)
class HappeningFiring:
    happening: HappeningId


@final
@dataclass(frozen=True)
class ReactionFiring:
    reaction: ReactionId


@final
@dataclass(frozen=True)
class JointActionSettling:
    joint_action: JointActionId
    completed: bool


@final
@dataclass(frozen=True)
class TimePassed:
    pass


@final
@dataclass(frozen=True)
class Waking:
    person: PersonId


@final
@dataclass(frozen=True)
class UnnamedCause:
    event_kinds: tuple[str, ...]


PerceptionCause = (
    ActionTaken
    | ActionFailed
    | HappeningFiring
    | ReactionFiring
    | JointActionSettling
    | TimePassed
    | Waking
    | UnnamedCause
)
