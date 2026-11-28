from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.accept_action import AcceptAction, AcceptActionCommand
from ai_rpg_world.game_world.application.accept_world_time_passage import (
    AcceptWorldTimePassage,
    AcceptWorldTimePassageCommand,
    WorldTimePassageReply,
)
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.enter_section import EnterSection, EnterSectionCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime
from ai_rpg_world.game_world.application.settle_world_conditions import SettleWorldConditions
from ai_rpg_world.game_world.domain.action.built_in_attempts import EnterSectionAttempt
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import Condition, NoText
from ai_rpg_world.game_world.domain.condition.connectives import NotCondition
from ai_rpg_world.game_world.domain.condition.person_conditions import IsInSectionCondition
from ai_rpg_world.game_world.domain.condition.subject import NamedPerson
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.ending_declaration import EndingDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Capacity, DescriptionText, FlagId, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.probability import Probability
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import (
    access_to,
    character,
    compose_world,
    nouns,
    refusal_texts,
    section,
    spot,
)

WORLD = WorldId("accepting_world")
ALICE = PersonId("alice")
BOB = PersonId("bob")
GEN = PersonId("gen")
WORLD_ENDED = RefusalCode("GAME_WORLD.WORLD_ALREADY_ENDED")
WORLD_ENDED_TEXT = "世界はもう終わった。"
CAGE = replace(section("cage", "landing"), capacity=Capacity(1))
BELL = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
GUST = FlagDeclaration(FlagId("gust_blew"), DescriptionText("風が吹いた"), initially_raised=False)
_ALICE_DECLARED = character("alice", "landing")
ALICE_IN_CAGE = IsInSectionCondition(NamedPerson(_ALICE_DECLARED), CAGE, NoText())


class WorldForAccepting:
    def __init__(self, *, ends_when: Condition = NotCondition(AlwaysHolds(), NoText())) -> None:
        self.design = compose_world(
            nouns(
                flags=[BELL, GUST],
                spots=[spot("landing")],
                sections=[CAGE],
                characters=[_ALICE_DECLARED, character("bob", "landing"), character("gen", "landing")],
            ),
            section_accesses=[access_to(CAGE)],
            happenings=(
                HappeningDeclaration(
                    HappeningId("bell_when_alice_boards"),
                    ALICE_IN_CAGE,
                    RaiseFlagEffect(BELL),
                    True,
                    NoNotice(),
                ),
                HappeningDeclaration(
                    HappeningId("gust"),
                    ChanceCondition(Probability(1.0), NoText()),
                    RaiseFlagEffect(GUST),
                    True,
                    NoNotice(),
                ),
            ),
            ending=EndingDeclaration(ends_when=ends_when),
            refusal_texts_=replace(
                refusal_texts(), world_state={WORLD_ENDED: TextWithUnassignedPeople(WORLD_ENDED_TEXT)}
            ),
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="accepting_world",
            scenario_hash="accepting_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=WORLD, design=self.design))
        self.events: list[DomainEvent] = []
        distributor = CommittedEventsDistributor()
        distributor.register_receiver(self)
        self.scope = CommandScope(self.store, distributor)
        settle = SettleWorldConditions(self.scope, self.design)
        self.accept_action = AcceptAction(self.scope, self.design, settle)
        self.accept_time = AcceptWorldTimePassage(PassWorldTime(self.scope), settle)
        self._enter_section = EnterSection(CarryOutAction(self.scope, self.design), self.design)

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.events.extend(events)

    def board_cage(self, actor: PersonId) -> ActionReply:
        attempt = EnterSectionAttempt(actor, self.design.section_access(CAGE.section_id))
        return self.accept_action(AcceptActionCommand(EnterSectionCommand(attempt), self._enter_section))

    def enter_section_without_settling(self, command: EnterSectionCommand) -> ActionReply:
        return self._enter_section(command)

    def pass_time(self) -> WorldTimePassageReply:
        return self.accept_time(AcceptWorldTimePassageCommand())

    def end_world(self) -> None:
        self.scope.run(lambda session: session.ending().end(session.clock().now()))
        self.events.clear()

    def now(self) -> WorldTick:
        return self.scope.run(lambda session: session.clock().now())

    def is_raised(self, flag: FlagDeclaration) -> bool:
        return self.scope.run(lambda session: session.facts().flags().is_raised(flag))

    def in_cage(self, person: PersonId) -> bool:
        return self.scope.run(lambda session: session.facts().whereabouts().is_in_section(PersonBody(person), CAGE))
