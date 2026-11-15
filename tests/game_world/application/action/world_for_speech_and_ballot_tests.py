from __future__ import annotations

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.cast_ballot import CastBallot, CastBallotCommand
from ai_rpg_world.game_world.application.action.speak import Speak, SpeakCommand
from ai_rpg_world.game_world.application.action.start_travel import StartTravel, StartTravelCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    GroupDecisionBallotAttempt,
    SpeechAttempt,
    TravelAttempt,
)
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, SpeechContent
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.game_world.domain.world_progress import Abstain, VoteFor
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.application.action.world_for_action_tests import BatchesReceived
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    group_decision,
    nouns,
    passage,
    spot,
)

WORLD = WorldId("speech_world")
HARU = PersonId("haru")
NATSU = PersonId("natsu")
SQUARE = spot("square")
WELL = spot("well")
PATH = passage("path", ("square", "well"), travel_ticks=3)
EXILE = group_decision("exile")


class WorldForSpeechAndBallots:
    def __init__(self) -> None:
        self.design = compose_world(
            nouns(
                spots=[SQUARE, WELL],
                passages=[PATH],
                characters=[character("haru", "square"), character("natsu", "square")],
                group_decisions=[EXILE],
            ),
            group_decision_rules=[everyone_votes_on(EXILE)],
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="speech_world",
            scenario_hash="speech_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=WORLD, design=self.design))
        distributor = CommittedEventsDistributor()
        self.received = BatchesReceived()
        distributor.register_receiver(self.received)
        self.scope = CommandScope(self.store, distributor)
        self.carry_out = CarryOutAction(self.scope, self.design)

    def say(self, actor: PersonId, text: str) -> ActionReply:
        attempt = SpeechAttempt(actor, OrdinaryVoice(), SpeechContent(text))
        return Speak(self.carry_out)(SpeakCommand(attempt))

    def vote(self, actor: PersonId, choice: VoteFor | Abstain) -> ActionReply:
        attempt = GroupDecisionBallotAttempt(actor, EXILE, choice)
        return CastBallot(self.carry_out)(CastBallotCommand(attempt))

    def travel(self, actor: PersonId, destination: SpotDeclaration) -> ActionReply:
        return StartTravel(self.carry_out, self.design)(StartTravelCommand(TravelAttempt(actor, destination)))

    def open_exile_vote(self) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates().group_decision(EXILE).start(frozenset({HARU, NATSU}), frozenset({HARU, NATSU}))
            )
        )

    def read(self) -> WorldSession:
        return self.store.session()

    def events(self) -> list[DomainEvent]:
        return [event for batch in self.received.batches for event in batch]
