from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, Protocol, final

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId


class FiredHappening(Protocol):
    @property
    def happening_id(self) -> HappeningId: ...


class FiredReaction(Protocol):
    @property
    def reaction_id(self) -> ReactionId: ...


class CompletedJointAction(Protocol):
    @property
    def joint_id(self) -> JointActionId: ...


def _no_subject(trigger: object, kind: SubjectKind) -> NoReturn:
    raise SubjectNotInTriggerException(f"{trigger!r} does not answer {kind.name}")


def _no_item(trigger: object) -> NoReturn:
    raise ItemNotInTriggerException(f"{trigger!r} does not answer the item")


@final
@dataclass(frozen=True)
class HappeningFired:
    happening: FiredHappening

    def person_as(self, kind: SubjectKind) -> PersonId:
        _no_subject(self, kind)

    def this_item(self) -> ItemInstanceId:
        _no_item(self)


@final
@dataclass(frozen=True)
class ReactionFired:
    reaction: FiredReaction

    def person_as(self, kind: SubjectKind) -> PersonId:
        _no_subject(self, kind)

    def this_item(self) -> ItemInstanceId:
        _no_item(self)


@final
@dataclass(frozen=True)
class JointActionCompleted:
    joint: CompletedJointAction

    def person_as(self, kind: SubjectKind) -> PersonId:
        _no_subject(self, kind)

    def this_item(self) -> ItemInstanceId:
        _no_item(self)


@final
@dataclass(frozen=True)
class GroupDecisionResult:
    decision: GroupDecisionDeclaration
    chosen: PersonId

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.CHOSEN_BY_GROUP:
            return self.chosen
        _no_subject(self, kind)

    def this_item(self) -> ItemInstanceId:
        _no_item(self)


@final
@dataclass(frozen=True)
class WorldTimePassing:
    tick: WorldTick

    def person_as(self, kind: SubjectKind) -> PersonId:
        _no_subject(self, kind)

    def this_item(self) -> ItemInstanceId:
        _no_item(self)


@final
@dataclass(frozen=True)
class EachPersonOf:
    outer: Trigger
    person: PersonId

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.EACH_PERSON:
            return self.person
        return self.outer.person_as(kind)

    def this_item(self) -> ItemInstanceId:
        return self.outer.this_item()


Trigger = (
    ActionAttempt
    | HappeningFired
    | ReactionFired
    | GroupDecisionResult
    | JointActionCompleted
    | WorldTimePassing
    | EachPersonOf
)
