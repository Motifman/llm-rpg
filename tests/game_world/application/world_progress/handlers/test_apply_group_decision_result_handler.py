from __future__ import annotations

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.world_progress.apply_group_decision_result import (
    ApplyGroupDecisionReached,
    ApplyGroupDecisionUnresolved,
)
from ai_rpg_world.game_world.application.world_progress.handlers.apply_group_decision_result_handler import (
    ApplyGroupDecisionResultHandler,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import GroupDecisionResult, GroupDecisionUnresolved, Trigger
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb import GroupDecisionRulesDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect, SequenceEffect
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.world_progress_effects import StartGroupDecisionEffect
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, PersonId
from ai_rpg_world.game_world.domain.world_progress import (
    GroupDecision,
    GroupDecisionReachedEvent,
    GroupDecisionUnresolvedEvent,
    VoteFor,
)
from ai_rpg_world.game_world.domain.world_records import WorldFlagRaisedEvent, WorldFlags
from tests.game_world.application.world_for_handler_tests import WORLD, WiredWorld
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import character, compose_world, group_decision, nouns, spot

AKI = PersonId("aki")
HARU = PersonId("haru")
NATSU = PersonId("natsu")
EXILE = group_decision("exile")
ROLL_CALL = group_decision("roll_call")
EXILED = FlagDeclaration(FlagId("someone_exiled"), DescriptionText("誰かが追放された"), initially_raised=False)
STALLED = FlagDeclaration(FlagId("vote_stalled"), DescriptionText("投票が決まらなかった"), initially_raised=False)
START_ROLL_CALL = StartGroupDecisionEffect(
    ROLL_CALL, voters=PeopleSelection(where=AlwaysHolds()), choices=PeopleSelection(where=AlwaysHolds())
)


class _RaisedBy:
    def __init__(self) -> None:
        self.triggers: list[Trigger] = []

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.triggers += [event.trigger for event in events if isinstance(event, WorldFlagRaisedEvent)]


def _world(*, when_decided: Effect, when_undecided: Effect) -> tuple[WiredWorld, _RaisedBy]:
    design = compose_world(
        nouns(
            flags=[EXILED, STALLED],
            spots=[spot("square")],
            characters=[character(person.value, "square") for person in (AKI, HARU, NATSU)],
            group_decisions=[EXILE, ROLL_CALL],
        ),
        group_decision_rules=[
            GroupDecisionRulesDeclaration(
                decision=EXILE,
                voters=PeopleSelection(where=AlwaysHolds()),
                choices=PeopleSelection(where=AlwaysHolds()),
                when_decided=when_decided,
                when_undecided=when_undecided,
            ),
            everyone_votes_on(ROLL_CALL),
        ],
    )
    exile = GroupDecision.not_started(EXILE)
    exile.start(frozenset({AKI, HARU}), frozenset({AKI, HARU, NATSU}))
    exile.cast(AKI, VoteFor(NATSU))
    roll_call = GroupDecision.not_started(ROLL_CALL)
    roll_call.start(frozenset({AKI}), frozenset({AKI}))
    world = WiredWorld(design, exile, roll_call, WorldFlags.start(WORLD))
    handler = ApplyGroupDecisionResultHandler(
        ApplyGroupDecisionReached(world.scope, design), ApplyGroupDecisionUnresolved(world.scope, design)
    )
    world.distributor.register_handler(GroupDecisionReachedEvent, handler)
    world.distributor.register_handler(GroupDecisionUnresolvedEvent, handler)
    raised_by = _RaisedBy()
    world.distributor.register_receiver(raised_by)
    return world, raised_by


def _haru_votes_for(person: PersonId) -> object:
    return lambda session: session.aggregates().group_decision(EXILE).cast(HARU, VoteFor(person))


def _raised(flag: FlagDeclaration) -> object:
    return lambda session: session.facts().flags().is_raised(flag)


def _exile_is_open(session: WorldSession) -> bool:
    return session.aggregates().group_decision(EXILE).is_open()


class TestApplyGroupDecisionResultHandler:
    """集団の決定が決まったとき・決まらなかったときに、それぞれの効果を当てる挙動を保証する。"""

    def test_effect_of_reached_decision_applies_with_the_chosen_person(self) -> None:
        """アキに続いてハルもナツに入れて決まると、when_decided で追放の旗が立ち、そのきっかけはナツを選んだ GroupDecisionResult。"""
        world, raised_by = _world(when_decided=RaiseFlagEffect(EXILED), when_undecided=RaiseFlagEffect(STALLED))

        world.scope.run(_haru_votes_for(NATSU))

        assert (world.read(_raised(EXILED)), world.read(_raised(STALLED))) == (True, False)
        assert raised_by.triggers == [GroupDecisionResult(EXILE, chosen=NATSU)]

    def test_effect_of_unresolved_decision_applies(self) -> None:
        """アキがナツに、ハルがアキに入れて同数で決まらないと、when_undecided で決まらなかった旗が立ち、そのきっかけは GroupDecisionUnresolved。"""
        world, raised_by = _world(when_decided=RaiseFlagEffect(EXILED), when_undecided=RaiseFlagEffect(STALLED))

        world.scope.run(_haru_votes_for(AKI))

        assert (world.read(_raised(EXILED)), world.read(_raised(STALLED))) == (False, True)
        assert raised_by.triggers == [GroupDecisionUnresolved(EXILE)]

    def test_refused_effect_rolls_back_only_the_handler_and_keeps_the_ballot(self) -> None:
        """when_decided が追放の旗を立ててから開いている点呼を始め直そうとして断られると、追放の旗は立たず、ハルの票で決まった投票は閉じたまま残り、断りが 1 つ数えられる。"""
        world, _ = _world(
            when_decided=SequenceEffect(steps=(RaiseFlagEffect(EXILED), START_ROLL_CALL)), when_undecided=NoEffect()
        )

        world.scope.run(_haru_votes_for(NATSU))

        assert (world.read(_raised(EXILED)), world.read(_exile_is_open)) == (False, False)
        assert world.distributor.refused_handlers == {
            ("ApplyGroupDecisionResultHandler", "GAME_WORLD.GROUP_DECISION_ALREADY_OPEN"): 1
        }
