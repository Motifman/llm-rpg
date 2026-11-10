from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.trigger_answers_nothing_by_default import TriggerAnswersNothingByDefault
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
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


class _NotAnAction(TriggerAnswersNothingByDefault):
    def acting_person(self) -> PersonId | NoActingPerson:
        return NoActingPerson()

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)


@final
@dataclass(frozen=True)
class HappeningFired(_NotAnAction):
    happening: FiredHappening


@final
@dataclass(frozen=True)
class ReactionFired(_NotAnAction):
    reaction: FiredReaction


@final
@dataclass(frozen=True)
class JointActionCompleted(_NotAnAction):
    joint: CompletedJointAction


@final
@dataclass(frozen=True)
class GroupDecisionResult(_NotAnAction):
    decision: GroupDecisionDeclaration
    chosen: PersonId

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.CHOSEN_BY_GROUP:
            return self.chosen
        return super().person_as(kind)


@final
@dataclass(frozen=True)
class WorldTimePassing(_NotAnAction):
    tick: WorldTick


@final
@dataclass(frozen=True)
class LookingAround(_NotAnAction):
    tick: WorldTick


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

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.outer.acting_person()

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId:
        return self.outer.argument(name)

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return self.outer.fall_cause_for(victim)


Trigger = (
    ActionAttempt
    | HappeningFired
    | ReactionFired
    | GroupDecisionResult
    | JointActionCompleted
    | WorldTimePassing
    | LookingAround
    | EachPersonOf
)
