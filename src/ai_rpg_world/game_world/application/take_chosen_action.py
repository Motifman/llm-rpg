from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import AgentMove
from ai_rpg_world.game_world.application.accept_action import AcceptAction, AcceptActionCommand
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.cast_ballot import CastBallot, CastBallotCommand
from ai_rpg_world.game_world.application.action.drop_item import DropItem, DropItemCommand
from ai_rpg_world.game_world.application.action.enter_section import EnterSection, EnterSectionCommand
from ai_rpg_world.game_world.application.action.hand_over_items import HandOverItems, HandOverItemsCommand
from ai_rpg_world.game_world.application.action.hold_item import HoldItem, HoldItemCommand
from ai_rpg_world.game_world.application.action.interact_with_carried_item import (
    InteractWithCarriedItem,
    InteractWithCarriedItemCommand,
)
from ai_rpg_world.game_world.application.action.interact_with_object import (
    InteractWithObject,
    InteractWithObjectCommand,
)
from ai_rpg_world.game_world.application.action.interact_with_person import (
    InteractWithPerson,
    InteractWithPersonCommand,
)
from ai_rpg_world.game_world.application.action.leave_section import LeaveSection, LeaveSectionCommand
from ai_rpg_world.game_world.application.action.listen import Listen, ListenCommand
from ai_rpg_world.game_world.application.action.pick_up_ground_item import PickUpGroundItem, PickUpGroundItemCommand
from ai_rpg_world.game_world.application.action.put_away_item import PutAwayItem, PutAwayItemCommand
from ai_rpg_world.game_world.application.action.search_spot import SearchSpot, SearchSpotCommand
from ai_rpg_world.game_world.application.action.speak import Speak, SpeakCommand
from ai_rpg_world.game_world.application.action.start_travel import StartTravel, StartTravelCommand
from ai_rpg_world.game_world.application.action.tend_fallen_person import TendFallenPerson, TendFallenPersonCommand
from ai_rpg_world.game_world.application.action.use_item import UseItem, UseItemCommand
from ai_rpg_world.game_world.application.action.wait import Wait, WaitCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.list_available_actions import ListAvailableActions
from ai_rpg_world.game_world.application.offer_action_choices import choice_wording_for
from ai_rpg_world.game_world.application.settle_world_conditions import SettleWorldConditions
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    GroundItemPickupAttempt,
    GroupDecisionBallotAttempt,
    HoldItemAttempt,
    ItemDropAttempt,
    ItemHandOverAttempt,
    ItemUseAttempt,
    LeaveSectionAttempt,
    ListeningAttempt,
    PutAwayItemAttempt,
    SpeechAttempt,
    SpotSearchAttempt,
    TendAttempt,
    TravelAttempt,
    WaitAttempt,
)
from ai_rpg_world.game_world.domain.action.chosen_action import (
    ChosenActionAttempts,
    ChosenActionReading,
    MisfitChosenAction,
)
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
)
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.value_object.world_tick import WorldTick


@final
@dataclass(frozen=True)
class TurnGuidance:
    person: PersonId
    text: str
    at: WorldTick


@final
@dataclass(frozen=True)
class TakeChosenActionCommand:
    person: PersonId
    move: AgentMove


@final
class TakeChosenAction:
    def __init__(self, scope: CommandScope, design: WorldDesign, settle: SettleWorldConditions) -> None:
        self._scope = scope
        self._design = design
        self._list = ListAvailableActions(scope, design)
        self._accept = AcceptAction(scope, design, settle)
        self._carry_out = CarryOutAction(scope, design)

    def __call__(self, command: TakeChosenActionCommand) -> ActionReply | TurnGuidance:
        chosen, now = self._scope.run(lambda session: self._read(session, command))
        entrances = _ActionEntrancesOf(self._accept, self._carry_out, self._design, command.person, now)
        return chosen.entered_through(entrances)

    def _read(
        self, session: WorldSession, command: TakeChosenActionCommand
    ) -> tuple[ChosenActionAttempts | MisfitChosenAction, WorldTick]:
        wording = choice_wording_for(session, command.person, self._design)
        reading = ChosenActionReading.of(command.person, self._list.available_in(session, command.person), wording)
        return reading.attempts_for(command.move), session.facts().now()


@final
class _ActionEntrancesOf:
    def __init__(
        self, accept: AcceptAction, carry_out: CarryOutAction, design: WorldDesign, person: PersonId, now: WorldTick
    ) -> None:
        self._accept = accept
        self._person = person
        self._now = now
        self._start_travel = StartTravel(carry_out, design)
        self._speak = Speak(carry_out)
        self._listen = Listen(carry_out)
        self._wait = Wait(carry_out)
        self._tend_fallen_person = TendFallenPerson(carry_out)
        self._hand_over_items = HandOverItems(carry_out)
        self._pick_up_ground_item = PickUpGroundItem(carry_out)
        self._drop_item = DropItem(carry_out)
        self._search_spot = SearchSpot(carry_out, design)
        self._use_item = UseItem(carry_out, design)
        self._enter_section = EnterSection(carry_out, design)
        self._leave_section = LeaveSection(carry_out, design)
        self._hold_item = HoldItem(carry_out)
        self._put_away_item = PutAwayItem(carry_out)
        self._cast_ballot = CastBallot(carry_out)
        self._interact_with_object = InteractWithObject(carry_out, design)
        self._interact_with_carried_item = InteractWithCarriedItem(carry_out, design)
        self._interact_with_person = InteractWithPerson(carry_out, design)

    def misfit(self, text: str) -> ActionReply | TurnGuidance:
        return TurnGuidance(self._person, text, self._now)

    def travel(self, attempt: TravelAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(StartTravelCommand(attempt), self._start_travel))

    def speak(self, attempt: SpeechAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(SpeakCommand(attempt), self._speak))

    def listen(self, attempt: ListeningAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(ListenCommand(attempt), self._listen))

    def wait(self, attempt: WaitAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(WaitCommand(attempt), self._wait))

    def tend(self, attempt: TendAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(TendFallenPersonCommand(attempt), self._tend_fallen_person))

    def hand_over(self, attempt: ItemHandOverAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(HandOverItemsCommand(attempt), self._hand_over_items))

    def pick_up(self, attempt: GroundItemPickupAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(PickUpGroundItemCommand(attempt), self._pick_up_ground_item))

    def drop(self, attempt: ItemDropAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(DropItemCommand(attempt), self._drop_item))

    def search_spot(self, attempt: SpotSearchAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(SearchSpotCommand(attempt), self._search_spot))

    def use_item(self, attempt: ItemUseAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(UseItemCommand(attempt), self._use_item))

    def enter_section(self, attempt: EnterSectionAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(EnterSectionCommand(attempt), self._enter_section))

    def leave_section(self, attempt: LeaveSectionAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(LeaveSectionCommand(attempt), self._leave_section))

    def hold(self, attempt: HoldItemAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(HoldItemCommand(attempt), self._hold_item))

    def put_away(self, attempt: PutAwayItemAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(PutAwayItemCommand(attempt), self._put_away_item))

    def cast_ballot(self, attempt: GroupDecisionBallotAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(CastBallotCommand(attempt), self._cast_ballot))

    def interact_with_object(self, attempt: ObjectInteractionAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(InteractWithObjectCommand(attempt), self._interact_with_object))

    def interact_with_carried_item(self, attempt: CarriedItemInteractionAttempt) -> ActionReply | TurnGuidance:
        return self._accept(
            AcceptActionCommand(InteractWithCarriedItemCommand(attempt), self._interact_with_carried_item)
        )

    def interact_with_person(self, attempt: PersonInteractionAttempt) -> ActionReply | TurnGuidance:
        return self._accept(AcceptActionCommand(InteractWithPersonCommand(attempt), self._interact_with_person))
