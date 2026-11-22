from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar, TypeVar, final

from typing_extensions import Self

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActorRequirement,
    CopresenceRequirement,
    DoesNotUseBody,
    Exertion,
    LivingOnly,
    LivingOrDeparted,
    UsesBody,
    WithCarriedItem,
    WithGroundItem,
    WithPerson,
)
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NoOneFoundInTheDark
from ai_rpg_world.game_world.domain.action.declared_section_access import DeclaredSectionAccess
from ai_rpg_world.game_world.domain.action.manner import Manner, Openly
from ai_rpg_world.game_world.domain.action.offered_action import (
    BALLOT,
    CONTENT,
    DECISION,
    DESTINATION,
    ITEM,
    RECIPIENT,
    SECTION_MOVE,
    TARGET,
    ActionChoiceKind,
    OfferedAction,
    OfferedFreeText,
    OfferedStep,
)
from ai_rpg_world.game_world.domain.action.speech import (
    OrdinaryVoice,
    Shout,
    SpeechContent,
    SpeechContentNotChosen,
    SpeechReach,
    Whisper,
)
from ai_rpg_world.game_world.domain.action.trigger_answers_nothing_by_default import TriggerAnswersNothingByDefault
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason, WaitReason
from ai_rpg_world.game_world.domain.action.witnessed_act import WitnessedAct, item_names
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.action_texts import ActionTextKey
from ai_rpg_world.game_world.domain.declaration.verb.default_duration import DefaultDuration
from ai_rpg_world.game_world.domain.exception.action_exception import (
    HandOverToSelfException,
    NothingToHandOverException,
    SeveralItemsNotOfferedException,
)
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    NoRouteToDestinationException,
    OccupantNotAtRouteStartException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.spot_search import SpotSearch
from ai_rpg_world.game_world.domain.perception import Noise, NoTarget
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import (
    InteractionId,
    ItemSpecId,
    ObjectId,
    PassageId,
    PersonId,
    SpotId,
    Ticks,
)
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, NoRoute, Occupant, PersonBody, Route
from ai_rpg_world.game_world.domain.world_progress.group_decision import Abstain, VoteFor

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_entrances import ActionEntrances
    from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
    from ai_rpg_world.game_world.domain.action.unavailable_object_operation import UnavailableObjectOperation
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
    from ai_rpg_world.game_world.domain.exception.game_world_exception import WorldRefusal
    from ai_rpg_world.game_world.domain.people import NameInText, TextAboutPeople, TextWithUnassignedPeople

_Reply = TypeVar("_Reply")


class _BuiltInAttempt(TriggerAnswersNothingByDefault):
    actor: PersonId
    _KIND: ClassVar[ActionKind]
    _CHOICE: ClassVar[ActionChoiceKind]

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        return OfferedAction(self._CHOICE)

    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self:
        return self

    def done_text_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> TextAboutPeople:
        return self._about_this_act(design.action_texts.done_of(self._text_key()), design, item_specs)

    def summary_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> TextAboutPeople:
        return self._about_this_act(design.action_texts.summary_of(self._text_key()), design, item_specs)

    def _text_key(self) -> ActionTextKey:
        return _TEXT_KEY_OF_KIND[self._KIND]

    def _about_this_act(
        self, text: TextWithUnassignedPeople, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]
    ) -> TextAboutPeople:
        target = self._target_in_texts()
        people = {"actor": self.actor} | ({"target": target} if isinstance(target, PersonId) else {})
        return text.about_named(people, self._names(design, item_specs))

    def _target_in_texts(self) -> PersonId | NoTarget:
        return self._witnessed_target()

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

    def operates(self, obj: ObjectId, interaction: InteractionId) -> bool:
        return False

    def hidden_while_unmet(self) -> bool:
        return False

    def unavailable_on_object(
        self, design: WorldDesign, reason: TextAboutPeople
    ) -> tuple[UnavailableObjectOperation, ...]:
        return ()

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

    def aimed_in(self, facts: WorldFacts) -> Self | NoOneFoundInTheDark:
        return self

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

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        return OfferedAction(self._CHOICE, (wording.item(ITEM, self.item),))


@final
@dataclass(frozen=True)
class TravelAttempt(_BuiltInAttempt):
    _KIND = ActionKind.TRAVEL
    _CHOICE = ActionChoiceKind.TRAVEL_TO

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.travel(self)

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

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        return OfferedAction(self._CHOICE, (OfferedStep(DESTINATION, self.destination.name),))


def _open_passages(facts: WorldFacts) -> frozenset[PassageId]:
    passages = facts.passages()
    return frozenset(passage.passage_id for passage in facts.nouns().all_passages() if passages.is_traversable(passage))


@final
@dataclass(frozen=True)
class SpeechAttempt(_BuiltInAttempt):
    _KIND = ActionKind.SPEAK
    _CHOICE = ActionChoiceKind.SPEAK

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.speak(self)

    actor: PersonId
    reach: SpeechReach
    content: SpeechContent | SpeechContentNotChosen

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return self.reach.copresence_requirements()

    def take_effect(self) -> Ticks:
        self._chosen_content()
        return Ticks(0)

    def witnessed_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> WitnessedAct:
        content = self._chosen_content()
        return WitnessedAct(
            perception=design.built_in_action_perceptions.speech(self.reach),
            names={"speech": content},
            target=self.reach.listener(),
            manner=Openly(),
            source=self.reach.voice(),
        )

    def can_start_while_busy(self) -> bool:
        return True

    def _text_key(self) -> ActionTextKey:
        return _TEXT_KEY_OF_REACH[type(self.reach)]

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {"speech": self._chosen_content()}

    def _witnessed_target(self) -> PersonId | NoTarget:
        return self.reach.listener()

    def _chosen_content(self) -> SpeechContent:
        return self.content.chosen_by(self.actor)

    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self:
        return replace(self, content=self.content.written_as(values))

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        return OfferedAction(self._CHOICE, self.reach.offered_steps(wording), (OfferedFreeText(CONTENT),))


@final
@dataclass(frozen=True)
class ListeningAttempt(_BuiltInAttempt):
    _KIND = ActionKind.LISTEN
    _CHOICE = ActionChoiceKind.LISTEN

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.listen(self)

    actor: PersonId

    def take_effect(self, facts: WorldFacts) -> Ticks:
        return facts.rules().duration_of(self._KIND, DefaultDuration())

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def actor_requirement(self) -> ActorRequirement:
        return LivingOrDeparted()


@final
@dataclass(frozen=True)
class WaitAttempt(_BuiltInAttempt):
    _KIND = ActionKind.WAIT
    _CHOICE = ActionChoiceKind.WAIT

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.wait(self)

    actor: PersonId
    reason: WaitReason | NoReason

    def take_effect(self) -> Ticks:
        return Ticks(0)

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def actor_requirement(self) -> ActorRequirement:
        return LivingOrDeparted()


@final
@dataclass(frozen=True)
class TendAttempt(_BuiltInAttempt):
    _KIND = ActionKind.TEND
    _CHOICE = ActionChoiceKind.TEND_TO_PLAYER

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.tend(self)

    actor: PersonId
    target: PersonId

    def exertion(self) -> Exertion:
        return UsesBody()

    def tend(self, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        facts.rules().tend.revive(world.vitals(self.target), facts.now())
        return facts.rules().duration_of(self._KIND, DefaultDuration())

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithPerson(self.target),)

    def _witnessed_target(self) -> PersonId | NoTarget:
        return self.target

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.TARGET:
            return self.target
        return super().person_as(kind)

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        return OfferedAction(self._CHOICE, (OfferedStep(TARGET, wording.person(self.target)),))


@final
@dataclass(frozen=True)
class ItemHandOverAttempt(_BuiltInAttempt):
    _KIND = ActionKind.HAND_OVER
    _CHOICE = ActionChoiceKind.GIVE_ITEM

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.hand_over(self)

    actor: PersonId
    to: PersonId
    items: tuple[ItemInstanceId, ...]
    manner: Manner

    def __post_init__(self) -> None:
        if not self.items:
            raise NothingToHandOverException(f"{self.actor.value} hands nothing over to {self.to.value}")
        if self.actor == self.to:
            raise HandOverToSelfException(f"{self.actor.value} hands items over to themselves")

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

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        if len(self.items) != 1:
            raise SeveralItemsNotOfferedException(
                f"a hand-over of {len(self.items)} items is not one of the action choices; offer one item at a time"
            )
        to = OfferedStep(RECIPIENT, wording.person(self.to))
        return OfferedAction(self._CHOICE, (to, wording.item(ITEM, self.items[0])))


@final
@dataclass(frozen=True)
class GroundItemPickupAttempt(_OnOneItem):
    _KIND = ActionKind.PICK_UP
    _CHOICE = ActionChoiceKind.PICKUP_ITEM

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.pick_up(self)

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
    _CHOICE = ActionChoiceKind.DROP_ITEM

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.drop(self)

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
    _CHOICE = ActionChoiceKind.EXPLORE

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.search_spot(self)

    actor: PersonId

    def exertion(self) -> Exertion:
        return UsesBody()

    def search(self, design: WorldDesign, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        location = facts.whereabouts().location_of(PersonBody(self.actor))
        if not isinstance(location, AtSpot):
            raise OccupantNotAtRouteStartException(f"{self.actor.value} is on the way and cannot search")
        SpotSearch(location.spot, design.discoverables_at(location.spot)).search_by(self.actor, facts, world, self)
        return facts.rules().duration_of(self._KIND, DefaultDuration())


@final
@dataclass(frozen=True)
class ItemUseAttempt(_OnOneItem):
    _KIND = ActionKind.USE_ITEM
    _CHOICE = ActionChoiceKind.USE_ITEM

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.use_item(self)

    actor: PersonId
    item: ItemInstanceId

    def exertion(self) -> Exertion:
        return UsesBody()

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithCarriedItem(self.item),)

    def take_effect(self, design: WorldDesign, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        design.use_of_item(facts.item(self.item).spec_id).apply(facts, world, self)
        return facts.rules().duration_of(self._KIND, DefaultDuration())


@final
@dataclass(frozen=True)
class EnterSectionAttempt(_BuiltInAttempt):
    _KIND = ActionKind.ENTER_SECTION
    _CHOICE = ActionChoiceKind.SET_SUB_LOCATION

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.enter_section(self)

    actor: PersonId
    access: DeclaredSectionAccess

    def exertion(self) -> Exertion:
        return self.access.exertion

    def _perception(self, design: WorldDesign) -> PerceptionDeclaration:
        return design.section_access(self.access.section.section_id).perceived_as

    def done_text_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> TextAboutPeople:
        written = design.section_access(self.access.section.section_id).enter_text
        return self._about_this_act(written, design, item_specs)

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {"section": self.access.section.name}

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        label = wording.design.section_access(self.access.section.section_id).enter_label
        return OfferedAction(self._CHOICE, (OfferedStep(SECTION_MOVE, label),))


@final
@dataclass(frozen=True)
class LeaveSectionAttempt(_BuiltInAttempt):
    _KIND = ActionKind.LEAVE_SECTION
    _CHOICE = ActionChoiceKind.SET_SUB_LOCATION

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.leave_section(self)

    actor: PersonId
    access: DeclaredSectionAccess

    def exertion(self) -> Exertion:
        return self.access.exertion

    def _perception(self, design: WorldDesign) -> PerceptionDeclaration:
        return design.section_access(self.access.section.section_id).perceived_as

    def done_text_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> TextAboutPeople:
        written = design.section_access(self.access.section.section_id).leave_text
        return self._about_this_act(written, design, item_specs)

    def _names(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> Mapping[str, NameInText]:
        return {"section": self.access.section.name}

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        label = wording.design.section_access(self.access.section.section_id).leave_label
        return OfferedAction(self._CHOICE, (OfferedStep(SECTION_MOVE, label),))


@final
@dataclass(frozen=True)
class HoldItemAttempt(_OnOneItem):
    _KIND = ActionKind.HOLD
    _CHOICE = ActionChoiceKind.HOLD_ITEM

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.hold(self)

    actor: PersonId
    item: ItemInstanceId

    def exertion(self) -> Exertion:
        return DoesNotUseBody()


@final
@dataclass(frozen=True)
class PutAwayItemAttempt(_OnOneItem):
    _KIND = ActionKind.PUT_AWAY
    _CHOICE = ActionChoiceKind.PUT_AWAY_ITEM

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.put_away(self)

    actor: PersonId
    item: ItemInstanceId

    def exertion(self) -> Exertion:
        return DoesNotUseBody()


@final
@dataclass(frozen=True)
class GroupDecisionBallotAttempt(_BuiltInAttempt):
    _KIND = ActionKind.CAST_BALLOT
    _CHOICE = ActionChoiceKind.VOTE

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.cast_ballot(self)

    actor: PersonId
    decision: GroupDecisionDeclaration
    choice: VoteFor | Abstain

    def exertion(self) -> Exertion:
        return DoesNotUseBody()

    def refusal_by_decision(self, facts: WorldFacts) -> WorldRefusal | None:
        return facts.group_decision(self.decision).ballot_refusal(self.actor, self.choice)

    def cast(self, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        world.group_decision(self.decision).cast(self.actor, self.choice)
        return facts.rules().duration_of(self.kind(), DefaultDuration())

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        choice = wording.person(self.choice.person) if isinstance(self.choice, VoteFor) else wording.abstain()
        return OfferedAction(self._CHOICE, (OfferedStep(DECISION, self.decision.name), OfferedStep(BALLOT, choice)))

    def _text_key(self) -> ActionTextKey:
        return ActionTextKey.VOTE_FOR if isinstance(self.choice, VoteFor) else ActionTextKey.CAST_BALLOT

    # 投票先は本人の要約にだけ書く。見ていた人への知らせには出さない (伏せた投票があるため)
    def _target_in_texts(self) -> PersonId | NoTarget:
        return self.choice.person if isinstance(self.choice, VoteFor) else NoTarget()


_TEXT_KEY_OF_KIND: Mapping[ActionKind, ActionTextKey] = {
    ActionKind.TRAVEL: ActionTextKey.TRAVEL,
    ActionKind.LISTEN: ActionTextKey.LISTEN,
    ActionKind.WAIT: ActionTextKey.WAIT,
    ActionKind.TEND: ActionTextKey.TEND,
    ActionKind.HAND_OVER: ActionTextKey.HAND_OVER,
    ActionKind.PICK_UP: ActionTextKey.PICK_UP,
    ActionKind.DROP: ActionTextKey.DROP,
    ActionKind.SEARCH: ActionTextKey.SEARCH,
    ActionKind.USE_ITEM: ActionTextKey.USE_ITEM,
    ActionKind.HOLD: ActionTextKey.HOLD,
    ActionKind.PUT_AWAY: ActionTextKey.PUT_AWAY,
    ActionKind.CAST_BALLOT: ActionTextKey.CAST_BALLOT,
    ActionKind.ENTER_SECTION: ActionTextKey.ENTER_SECTION,
    ActionKind.LEAVE_SECTION: ActionTextKey.LEAVE_SECTION,
}
_TEXT_KEY_OF_REACH: Mapping[type[SpeechReach], ActionTextKey] = {
    Whisper: ActionTextKey.WHISPER,
    OrdinaryVoice: ActionTextKey.SPEAK,
    Shout: ActionTextKey.SHOUT,
}
