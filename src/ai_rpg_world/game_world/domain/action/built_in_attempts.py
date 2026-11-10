from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActorRequirement,
    CopresenceRequirement,
    DoesNotUseBody,
    Exertion,
    LivingOnly,
    LivingOrDeparted,
    UsesBody,
    WithGroundItem,
    WithPerson,
)
from ai_rpg_world.game_world.domain.action.declared_section_access import DeclaredSectionAccess
from ai_rpg_world.game_world.domain.action.delivery import Delivery
from ai_rpg_world.game_world.domain.action.manner import Manner
from ai_rpg_world.game_world.domain.action.speech import SpeechContent, SpeechReach
from ai_rpg_world.game_world.domain.action.trigger_answers_nothing_by_default import TriggerAnswersNothingByDefault
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason, WaitReason
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.exception.action_exception import NoDeliveriesException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, PersonId
from ai_rpg_world.game_world.domain.world_progress.group_decision import Abstain, VoteFor


class _BuiltInAttempt(TriggerAnswersNothingByDefault):
    actor: PersonId
    _KIND: ClassVar[ActionKind]

    def kind(self) -> ActionKind:
        return self._KIND

    def actor_requirement(self) -> ActorRequirement:
        return LivingOnly()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return ()

    def can_start_while_busy(self) -> bool:
        return False

    def is_allowed_in(self, stage: WorldStageDeclaration | NoWorldStages) -> bool:
        return stage.allows(self._KIND)

    def done_as(self) -> frozenset[ActionKind | InteractionId]:
        return frozenset({self._KIND})

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.ACTOR:
            return self.actor
        return super().person_as(kind)

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.actor

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)


class _OnOneItem(_BuiltInAttempt):
    item: ItemInstanceId

    def this_item(self) -> ItemInstanceId:
        return self.item


@final
@dataclass(frozen=True)
class TravelAttempt(_BuiltInAttempt):
    _KIND = ActionKind.TRAVEL
    actor: PersonId
    destination: SpotDeclaration

    def exertion(self) -> Exertion:
        return UsesBody()

    def actor_requirement(self) -> ActorRequirement:
        return LivingOrDeparted()


@final
@dataclass(frozen=True)
class SpeechAttempt(_BuiltInAttempt):
    _KIND = ActionKind.SPEAK
    actor: PersonId
    reach: SpeechReach
    content: SpeechContent

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return self.reach.copresence_requirements()

    def can_start_while_busy(self) -> bool:
        return True


@final
@dataclass(frozen=True)
class ListeningAttempt(_BuiltInAttempt):
    _KIND = ActionKind.LISTEN
    actor: PersonId

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def actor_requirement(self) -> ActorRequirement:
        return LivingOrDeparted()


@final
@dataclass(frozen=True)
class WaitAttempt(_BuiltInAttempt):
    _KIND = ActionKind.WAIT
    actor: PersonId
    reason: WaitReason | NoReason

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def actor_requirement(self) -> ActorRequirement:
        return LivingOrDeparted()


@final
@dataclass(frozen=True)
class TendAttempt(_BuiltInAttempt):
    _KIND = ActionKind.TEND
    actor: PersonId
    target: PersonId

    def exertion(self) -> Exertion:
        return UsesBody()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithPerson(self.target),)

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.TARGET:
            return self.target
        return super().person_as(kind)


@final
@dataclass(frozen=True)
class ItemHandOverAttempt(_BuiltInAttempt):
    _KIND = ActionKind.HAND_OVER
    actor: PersonId
    deliveries: tuple[Delivery, ...]
    manner: Manner

    def __post_init__(self) -> None:
        if not self.deliveries:
            raise NoDeliveriesException(f"{self.actor.value} hands over nothing")

    def exertion(self) -> Exertion:
        return UsesBody()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        recipients = dict.fromkeys(delivery.to for delivery in self.deliveries)
        return tuple(WithPerson(recipient) for recipient in recipients)


@final
@dataclass(frozen=True)
class GroundItemPickupAttempt(_OnOneItem):
    _KIND = ActionKind.PICK_UP
    actor: PersonId
    item: ItemInstanceId
    manner: Manner

    def exertion(self) -> Exertion:
        return UsesBody()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithGroundItem(self.item),)


@final
@dataclass(frozen=True)
class ItemDropAttempt(_OnOneItem):
    _KIND = ActionKind.DROP
    actor: PersonId
    item: ItemInstanceId
    manner: Manner

    def exertion(self) -> Exertion:
        return UsesBody()


@final
@dataclass(frozen=True)
class SpotSearchAttempt(_BuiltInAttempt):
    _KIND = ActionKind.SEARCH
    actor: PersonId

    def exertion(self) -> Exertion:
        return UsesBody()


@final
@dataclass(frozen=True)
class ItemUseAttempt(_OnOneItem):
    _KIND = ActionKind.USE_ITEM
    actor: PersonId
    item: ItemInstanceId

    def exertion(self) -> Exertion:
        return UsesBody()


@final
@dataclass(frozen=True)
class EnterSectionAttempt(_BuiltInAttempt):
    _KIND = ActionKind.ENTER_SECTION
    actor: PersonId
    access: DeclaredSectionAccess

    def exertion(self) -> Exertion:
        return self.access.exertion


@final
@dataclass(frozen=True)
class LeaveSectionAttempt(_BuiltInAttempt):
    _KIND = ActionKind.LEAVE_SECTION
    actor: PersonId
    access: DeclaredSectionAccess

    def exertion(self) -> Exertion:
        return self.access.exertion


@final
@dataclass(frozen=True)
class HoldItemAttempt(_OnOneItem):
    _KIND = ActionKind.HOLD
    actor: PersonId
    item: ItemInstanceId

    def exertion(self) -> Exertion:
        return DoesNotUseBody()


@final
@dataclass(frozen=True)
class PutAwayItemAttempt(_OnOneItem):
    _KIND = ActionKind.PUT_AWAY
    actor: PersonId
    item: ItemInstanceId

    def exertion(self) -> Exertion:
        return DoesNotUseBody()


@final
@dataclass(frozen=True)
class GroupDecisionBallotAttempt(_BuiltInAttempt):
    _KIND = ActionKind.CAST_BALLOT
    actor: PersonId
    decision: GroupDecisionDeclaration
    choice: VoteFor | Abstain

    def exertion(self) -> Exertion:
        return DoesNotUseBody()
