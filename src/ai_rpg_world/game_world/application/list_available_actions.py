from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, final

from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.drop_item import DropItem
from ai_rpg_world.game_world.application.action.enter_section import EnterSection
from ai_rpg_world.game_world.application.action.hand_over_items import HandOverItems
from ai_rpg_world.game_world.application.action.hold_item import HoldItem
from ai_rpg_world.game_world.application.action.interact_with_carried_item import InteractWithCarriedItem
from ai_rpg_world.game_world.application.action.interact_with_object import InteractWithObject
from ai_rpg_world.game_world.application.action.interact_with_person import InteractWithPerson
from ai_rpg_world.game_world.application.action.leave_section import LeaveSection
from ai_rpg_world.game_world.application.action.pick_up_ground_item import PickUpGroundItem
from ai_rpg_world.game_world.application.action.put_away_item import PutAwayItem
from ai_rpg_world.game_world.application.action.search_spot import SearchSpot
from ai_rpg_world.game_world.application.action.speak import Speak
from ai_rpg_world.game_world.application.action.start_travel import StartTravel
from ai_rpg_world.game_world.application.action.tend_fallen_person import TendFallenPerson
from ai_rpg_world.game_world.application.action.use_item import UseItem
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_candidates import ActionCandidates
from ai_rpg_world.game_world.domain.action.action_prerequisite_check import (
    ActionPrecondition,
    ActionPrerequisiteCheck,
    CommonRulesOnly,
)
from ai_rpg_world.game_world.domain.action.available_actions import AvailableAction, AvailableActions
from ai_rpg_world.game_world.domain.action.built_in_attempts import GroupDecisionBallotAttempt
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import PersonId

_Attempt = TypeVar("_Attempt", bound=ActionAttempt)


@final
@dataclass(frozen=True)
class ListAvailableActionsCommand:
    person: PersonId


@final
class ListAvailableActions:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design
        carry_out = CarryOutAction(scope, design)
        self._search_spot = SearchSpot(carry_out, design)
        self._speak = Speak(carry_out)
        self._start_travel = StartTravel(carry_out, design)
        self._pick_up = PickUpGroundItem(carry_out)
        self._drop = DropItem(carry_out)
        self._hold = HoldItem(carry_out)
        self._put_away = PutAwayItem(carry_out)
        self._use_item = UseItem(carry_out, design)
        self._tend = TendFallenPerson(carry_out)
        self._hand_over = HandOverItems(carry_out)
        self._enter_section = EnterSection(carry_out, design)
        self._leave_section = LeaveSection(carry_out, design)
        self._interact_with_object = InteractWithObject(carry_out, design)
        self._interact_with_carried_item = InteractWithCarriedItem(carry_out, design)
        self._interact_with_person = InteractWithPerson(carry_out, design)

    def __call__(self, command: ListAvailableActionsCommand) -> AvailableActions:
        return self._scope.run(lambda session: self.available_in(session, command.person))

    def available_in(self, session: WorldSession, person: PersonId) -> AvailableActions:
        facts = session.facts()
        seen = VisibleSurroundings.seen_by_person(person, facts, self._design)
        candidates = ActionCandidates(person, seen, facts, self._design)
        judge = _Judge(facts, self._design.refusal_texts)
        return AvailableActions(
            actions=(
                *judge(candidates.spot_searches(), self._search_spot),
                *judge(candidates.waiting(), CommonRulesOnly()),
                *judge(candidates.speeches(), self._speak),
                *judge(candidates.travels(), self._start_travel),
                *judge(candidates.pickups(), self._pick_up),
                *judge(candidates.drops(), self._drop),
                *judge(candidates.holds(), self._hold),
                *judge(candidates.put_aways(), self._put_away),
                *judge(candidates.item_uses(), self._use_item),
                *judge(candidates.tends(), self._tend),
                *judge(candidates.hand_overs(), self._hand_over),
                *judge(candidates.section_entries(), self._enter_section),
                *judge(candidates.section_exits(), self._leave_section),
                *judge(candidates.object_interactions(), self._interact_with_object),
                *judge(candidates.carried_item_interactions(), self._interact_with_carried_item),
                *judge(candidates.person_interactions(), self._interact_with_person),
                *judge.ballots(candidates.ballots()),
                # 相手を選ぶとくじが進むので選ばない。相手の決まらない前提は確かめようがない。
                *judge(candidates.interactions_in_the_dark(), CommonRulesOnly()),
            )
        )


@final
class _Judge:
    def __init__(self, facts: WorldFacts, refusal_texts: RefusalTexts) -> None:
        self._facts = facts
        self._texts = refusal_texts
        self._check = ActionPrerequisiteCheck()

    def __call__(
        self, attempts: tuple[_Attempt, ...], precondition: ActionPrecondition[_Attempt]
    ) -> tuple[AvailableAction, ...]:
        return tuple(
            offered
            for attempt in attempts
            for offered in self._check.offered(attempt, precondition, self._facts, self._texts)
        )

    def ballots(self, attempts: tuple[GroupDecisionBallotAttempt, ...]) -> tuple[AvailableAction, ...]:
        return tuple(self._check.available_ballot(attempt, self._facts, self._texts) for attempt in attempts)
