from __future__ import annotations

from dataclasses import dataclass, replace

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.enter_section import EnterSection, EnterSectionCommand
from ai_rpg_world.game_world.application.action.leave_section import LeaveSection, LeaveSectionCommand
from ai_rpg_world.game_world.application.action.start_travel import StartTravel, StartTravelCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    LeaveSectionAttempt,
    TravelAttempt,
)
from ai_rpg_world.game_world.domain.action.trigger import Trigger
from ai_rpg_world.game_world.domain.condition.condition import AwaitsArguments, FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.passage_traversal_declaration import (
    PassageTraversalDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Capacity, PersonId, WorldId
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import (
    access_to,
    character,
    compose_world,
    nouns,
    passage,
    section,
    spot,
)

WORLD = WorldId("action_world")
ALICE = PersonId("alice")
BOB = PersonId("bob")
LANDING = spot("landing")
SHAFT = spot("shaft")
ADIT = spot("adit")
GALLERY = spot("gallery")
LADDER = passage("ladder", ("landing", "shaft"), travel_ticks=3)
DRIFT = passage("drift", ("shaft", "adit"))
GATE = passage("gate", ("landing", "gallery"))
CAGE = replace(section("cage", "landing"), capacity=Capacity(1))
LOFT = section("loft", "landing")
GATE_CLOSED_TEXT = "柵が閉まっていて通れない。"


@dataclass(frozen=True)
class GateIsShut:
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return False

    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def failure_reason_before_arguments(
        self, facts: WorldFacts, trigger: Trigger
    ) -> FailureReason | HiddenFailure | AwaitsArguments | None:
        return self.failure_reason(facts, trigger)

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        return FailureReason(ConditionPath.root(), TextAboutPeople(TextWithUnassignedPeople(GATE_CLOSED_TEXT), {}))

    def explains_failure(self) -> bool:
        return True


class BatchesReceived:
    def __init__(self) -> None:
        self.batches: list[tuple[DomainEvent, ...]] = []

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.batches.append(events)


class WorldForActions:
    def __init__(self) -> None:
        self.design = _design()
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="action_world",
            scenario_hash="action_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=WORLD, design=self.design))
        distributor = CommittedEventsDistributor()
        self.received = BatchesReceived()
        distributor.register_receiver(self.received)
        self.scope = CommandScope(self.store, distributor)
        self.carry_out = CarryOutAction(self.scope, self.design)

    def enter_cage(self, actor: PersonId) -> ActionReply:
        return self.enter(actor, CAGE)

    def enter(self, actor: PersonId, declared_section: SpotSectionDeclaration) -> ActionReply:
        access = self.design.section_access(declared_section.section_id)
        return EnterSection(self.carry_out, self.design)(EnterSectionCommand(EnterSectionAttempt(actor, access)))

    def leave_cage(self, actor: PersonId) -> ActionReply:
        access = self.design.section_access(CAGE.section_id)
        return LeaveSection(self.carry_out, self.design)(LeaveSectionCommand(LeaveSectionAttempt(actor, access)))

    def travel(self, actor: PersonId, destination: SpotDeclaration) -> ActionReply:
        return StartTravel(self.carry_out, self.design)(StartTravelCommand(TravelAttempt(actor, destination)))

    def pass_ticks(self, count: int) -> None:
        for _ in range(count):
            self.scope.run(lambda session: session.clock().advance(self.design.day_night, session.facts()))

    def read(self) -> WorldSession:
        return self.store.session()

    def events(self) -> list[DomainEvent]:
        return [event for batch in self.received.batches for event in batch]


def _design() -> WorldDesign:
    return compose_world(
        nouns(
            spots=[LANDING, SHAFT, ADIT, GALLERY],
            passages=[LADDER, DRIFT, GATE],
            sections=[CAGE, LOFT],
            characters=[character("alice", "landing"), character("bob", "landing")],
        ),
        section_accesses=[access_to(CAGE), replace(access_to(LOFT), entry_condition=GateIsShut())],
        passage_traversals=[PassageTraversalDeclaration(passage=GATE, condition=GateIsShut())],
    )
