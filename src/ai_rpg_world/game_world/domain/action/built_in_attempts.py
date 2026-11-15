from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, final

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
from ai_rpg_world.game_world.domain.action.manner import Manner, Openly
from ai_rpg_world.game_world.domain.action.speech import SpeechContent, SpeechReach
from ai_rpg_world.game_world.domain.action.trigger_answers_nothing_by_default import TriggerAnswersNothingByDefault
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason, WaitReason
from ai_rpg_world.game_world.domain.action.witnessed_act import WitnessedAct, item_names
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.exception.action_exception import NothingToHandOverException
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    NoRouteToDestinationException,
    OccupantNotAtRouteStartException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.perception import Noise, NoTarget
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, ItemSpecId, PassageId, PersonId, SpotId, Ticks
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, NoRoute, Occupant, Route
from ai_rpg_world.game_world.domain.world_progress.group_decision import Abstain, VoteFor

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
    from ai_rpg_world.game_world.domain.people import NameInText


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

    def items_handled(self) -> tuple[ItemInstanceId, ...]:
        return ()

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.ACTOR:
            return self.actor
        return super().person_as(kind)

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.actor

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)

    def witnessed_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> WitnessedAct:
        return WitnessedAct(
            perception=self._perception(design),
            names=self._names(design, item_specs),
            target=self._witnessed_target(),
            manner=self._witnessed_manner(),
            source=Noise(),
        )

    def _perception(self, design: WorldDesign) -> PerceptionDeclaration:
        return design.built_in_action_perceptions.of_kind(self._KIND)

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {}

    def _witnessed_target(self) -> PersonId | NoTarget:
        return NoTarget()

    def _witnessed_manner(self) -> Manner:
        return Openly()


class _OnOneItem(_BuiltInAttempt):
    item: ItemInstanceId

    def this_item(self) -> ItemInstanceId:
        return self.item

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {"item": item_names((self.item,), item_specs, design)}

    def items_handled(self) -> tuple[ItemInstanceId, ...]:
        return (self.item,)


@final
@dataclass(frozen=True)
class TravelAttempt(_BuiltInAttempt):
    _KIND = ActionKind.TRAVEL
    actor: PersonId
    destination: SpotDeclaration

    def exertion(self) -> Exertion:
        return UsesBody()

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {"destination": self.destination.name}

    def actor_requirement(self) -> ActorRequirement:
        return LivingOrDeparted()

    def unmet_route_condition(self, design: WorldDesign, facts: WorldFacts) -> FailureReason | HiddenFailure | None:
        start = self._start(facts)
        if isinstance(design.route(start, self.destination.spot_id, self._passable(design, facts)), Route):
            return None
        route_by_state = design.route(start, self.destination.spot_id, _open_passages(facts))
        if isinstance(route_by_state, NoRoute):
            return None
        for passage in route_by_state.passages:
            failure = design.passage_traversal(passage.passage_id).failure_reason(facts, self)
            if failure is not None:
                return failure
        return None

    def set_off(self, design: WorldDesign, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        route = design.route(self._start(facts), self.destination.spot_id, self._passable(design, facts))
        if isinstance(route, NoRoute):
            raise NoRouteToDestinationException(f"{self.actor.value} has no route to {self.destination.spot_id.value}")
        world.whereabouts().start_travel(self._occupant(facts), route)
        return route.total_ticks()

    def _occupant(self, facts: WorldFacts) -> Occupant:
        return facts.vitals(self.actor).occupant_in_world(facts.rules().departed_persons_act)

    def _start(self, facts: WorldFacts) -> SpotId:
        location = facts.whereabouts().location_of(self._occupant(facts))
        if not isinstance(location, AtSpot):
            raise OccupantNotAtRouteStartException(f"{self.actor.value} is not at any spot")
        return location.spot

    def _passable(self, design: WorldDesign, facts: WorldFacts) -> frozenset[PassageId]:
        return frozenset(
            passage for passage in _open_passages(facts) if design.passage_traversal(passage).holds(facts, self)
        )


def _open_passages(facts: WorldFacts) -> frozenset[PassageId]:
    passages = facts.passages()
    return frozenset(passage.passage_id for passage in facts.nouns().all_passages() if passages.is_traversable(passage))


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

    def witnessed_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> WitnessedAct:
        return WitnessedAct(
            perception=design.built_in_action_perceptions.speech(self.reach),
            names={"speech": self.content},
            target=self.reach.listener(),
            manner=Openly(),
            source=self.reach.voice(),
        )

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

    def _witnessed_target(self) -> PersonId | NoTarget:
        return self.target

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.TARGET:
            return self.target
        return super().person_as(kind)


@final
@dataclass(frozen=True)
class ItemHandOverAttempt(_BuiltInAttempt):
    _KIND = ActionKind.HAND_OVER
    actor: PersonId
    to: PersonId
    items: tuple[ItemInstanceId, ...]
    manner: Manner

    def __post_init__(self) -> None:
        if not self.items:
            raise NothingToHandOverException(f"{self.actor.value} hands nothing over to {self.to.value}")

    def exertion(self) -> Exertion:
        return UsesBody()

    def items_handled(self) -> tuple[ItemInstanceId, ...]:
        return self.items

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithPerson(self.to),)

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {"item": item_names(self.items, item_specs, design)}

    def _witnessed_target(self) -> PersonId | NoTarget:
        return self.to

    def _witnessed_manner(self) -> Manner:
        return self.manner

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.TARGET:
            return self.to
        return super().person_as(kind)


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

    def _witnessed_manner(self) -> Manner:
        return self.manner


@final
@dataclass(frozen=True)
class ItemDropAttempt(_OnOneItem):
    _KIND = ActionKind.DROP
    actor: PersonId
    item: ItemInstanceId
    manner: Manner

    def exertion(self) -> Exertion:
        return UsesBody()

    def _witnessed_manner(self) -> Manner:
        return self.manner


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

    def _perception(self, design: WorldDesign) -> PerceptionDeclaration:
        return design.section_access(self.access.section.section_id).perceived_as


@final
@dataclass(frozen=True)
class LeaveSectionAttempt(_BuiltInAttempt):
    _KIND = ActionKind.LEAVE_SECTION
    actor: PersonId
    access: DeclaredSectionAccess

    def exertion(self) -> Exertion:
        return self.access.exertion

    def _perception(self, design: WorldDesign) -> PerceptionDeclaration:
        return design.section_access(self.access.section.section_id).perceived_as


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
