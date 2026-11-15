from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.world_progress.apply_group_decision_result import (
    ApplyGroupDecisionReached,
    ApplyGroupDecisionUnresolved,
)
from ai_rpg_world.game_world.application.world_progress.handlers.apply_group_decision_reached_handler import (
    ApplyGroupDecisionReachedHandler,
)
from ai_rpg_world.game_world.application.world_progress.handlers.apply_group_decision_unresolved_handler import (
    ApplyGroupDecisionUnresolvedHandler,
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


class RaisedBy:
    def __init__(self) -> None:
        self.triggers: list[Trigger] = []

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.triggers += [event.trigger for event in events if isinstance(event, WorldFlagRaisedEvent)]


def exile_vote_world(*, when_decided: Effect, when_undecided: Effect) -> tuple[WiredWorld, RaisedBy]:
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
    world.distributor.register_handler(
        GroupDecisionReachedEvent, ApplyGroupDecisionReachedHandler(ApplyGroupDecisionReached(world.scope, design))
    )
    world.distributor.register_handler(
        GroupDecisionUnresolvedEvent,
        ApplyGroupDecisionUnresolvedHandler(ApplyGroupDecisionUnresolved(world.scope, design)),
    )
    raised_by = RaisedBy()
    world.distributor.register_receiver(raised_by)
    return world, raised_by


def haru_votes_for(person: PersonId) -> Callable[[WorldSession], None]:
    return lambda session: session.aggregates().group_decision(EXILE).cast(HARU, VoteFor(person))


def raised(flag: FlagDeclaration) -> Callable[[WorldSession], bool]:
    return lambda session: session.facts().flags().is_raised(flag)


def exile_is_open(session: WorldSession) -> bool:
    return session.aggregates().group_decision(EXILE).is_open()
