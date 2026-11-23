from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import cast

from ai_rpg_world.being.application.choose_action import ActionChoosingCompletion, ChooseAction
from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.application.end_being_turn import EndBeingTurn
from ai_rpg_world.being.application.enter_environment import EnterEnvironment
from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.application.leave_environment import LeaveEnvironment
from ai_rpg_world.being.application.memo_argument import MEMO_FIELD_NAME
from ai_rpg_world.being.application.perceive_observation import PerceiveObservation
from ai_rpg_world.being.application.prepare_being import PrepareBeing
from ai_rpg_world.being.application.receive_action_result import ReceiveActionResult
from ai_rpg_world.being.application.write_episodes_on_leaving import WriteEpisodesOnLeaving
from ai_rpg_world.being.application.writing_circumstances import CircumstancesOfBeings
from ai_rpg_world.being.contract import OfferedBeingTools
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.working_memory import Closing
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_visited_places_repository import InMemoryVisitedPlacesRepository
from ai_rpg_world.being.infrastructure.memory_writing_on_threads import MemoryWritingOnThreads
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.game_world.application.accept_world_time_passage import AcceptWorldTimePassage
from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson
from ai_rpg_world.game_world.application.check_readiness_to_act import CheckReadinessToAct
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception
from ai_rpg_world.game_world.application.deliver_perception_of_committed_events import (
    DeliverPerceptionOfCommittedEvents,
)
from ai_rpg_world.game_world.application.describe_action_result import DescribeActionResult
from ai_rpg_world.game_world.application.describe_scene import DescribeScene
from ai_rpg_world.game_world.application.mark_body_as_shown import MarkBodyAsShown
from ai_rpg_world.game_world.application.name_person import NamePerson
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.offer_action_choices import OfferActionChoices
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime
from ai_rpg_world.game_world.application.settle_world_conditions import SettleWorldConditions
from ai_rpg_world.game_world.application.take_chosen_action import TakeChosenAction
from ai_rpg_world.game_world.application.tell_current_time import TellCurrentTime
from ai_rpg_world.game_world.application.world_has_ended import WorldHasEnded
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenWithoutActor,
    SightStimulus,
    SightTexts,
)
from ai_rpg_world.game_world.domain.perception.people_present import WhoeverIsThere
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from ai_rpg_world.play_session.application.beings_taking_turns import BeingsTakingTurnsOneByOne
from ai_rpg_world.play_session.application.end_play_session import EndPlaySession, EndPlaySessionCommand
from ai_rpg_world.play_session.application.hand_observation_to_being import HandObservationToBeing
from ai_rpg_world.play_session.application.play_rounds import PlayRounds, TurnTakers
from ai_rpg_world.play_session.application.start_play_session import StartPlaySession, StartPlaySessionCommand
from ai_rpg_world.play_session.domain.cast import BeingCastInWorldEvent
from ai_rpg_world.play_session.domain.turn_rounds import RoundCount, TurnRoundsEvent
from ai_rpg_world.play_session.infrastructure.in_memory_cast_repository import InMemoryCastRepository
from ai_rpg_world.play_session.infrastructure.in_memory_turn_rounds_repository import InMemoryTurnRoundsRepository
from ai_rpg_world.play_session.infrastructure.roles_from_scenario import casting_by_person_name, roles_from_scenario
from tests.event_handoff_helpers import discard_events
from tests.game_world.support.perception_reports import PerceptionReportsReceived

_MINE_VILLAGE = Path(__file__).parents[2] / "data" / "scenarios" / "mine_village_v2.yaml"
WORLD = WorldId("mine_village_v2#1")
ENVIRONMENT_NAME = "廃坑の山村"


@cache
def _scenario() -> LoadedScenario:
    return load_scenario(_MINE_VILLAGE)


class _OpenWorldNoticed:
    def __init__(self, open_world: OpenWorld, on_opening: Callable[[], None]) -> None:
        self._open_world = open_world
        self._on_opening = on_opening

    def __call__(self, command: OpenWorldCommand) -> None:
        self._on_opening()
        self._open_world(command)


class MineVillageSession:
    """廃坑の山村 v2 を開き、4 人の Being を用意して入れたところ。"""

    def __init__(
        self,
        *,
        without: tuple[str, ...] = (),
        round_limit: int = 100,
        wake_waiting_after: int = 3,
        on_opening_world: Callable[[], None] = lambda: None,
        delivers_world_events: bool = False,
    ) -> None:
        scenario = _scenario()
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="mine_village_v2",
            scenario_hash="mine_village_v2",
            design=scenario.design,
            random=SeedableRandomSource(0),
        )
        self.beings = InMemoryBeingRepository()
        self.acquaintances = InMemoryAcquaintanceRepository()
        self.clock = InMemoryMemoryTurnClock()
        self.cast_events: list[BeingCastInWorldEvent] = []
        self.casts = InMemoryCastRepository(handoff=self.cast_events.extend)
        self.turn_round_events: list[TurnRoundsEvent] = []
        self.turn_rounds = InMemoryTurnRoundsRepository(handoff=self.turn_round_events.extend)
        distributor = CommittedEventsDistributor()
        self.scope = scope = CommandScope(self.store, distributor)
        self.start = StartPlaySession(
            open_world=cast(OpenWorld, _OpenWorldNoticed(OpenWorld(self.store), on_opening_world)),
            name_person=NamePerson(scope),
            brief=BriefEnteringPerson(scenario.design),
            prepare_being=PrepareBeing(self.beings),
            enter_environment=EnterEnvironment(self.beings, self.acquaintances, self.clock),
            casts=self.casts,
            turn_rounds=self.turn_rounds,
        )
        self.command = StartPlaySessionCommand(
            open_world=OpenWorldCommand(world_id=WORLD, design=scenario.design),
            environment_name=ENVIRONMENT_NAME,
            roles=tuple(role for role in roles_from_scenario(scenario) if role.person.value not in without),
            casting=casting_by_person_name(scenario),
            round_limit=RoundCount(round_limit),
            wake_waiting_after=RoundCount(wake_waiting_after),
        )

        self.memory_writing = MemoryWritingOnThreads(wait_limit_seconds=2.0)
        self.short_term_memories = InMemoryShortTermMemoryRepository(handoff=self.memory_writing.handoff)
        day_night = scenario.design.day_night
        assert isinstance(day_night, DayNightDeclaration)
        receiver = HandObservationToBeing(
            WORLD, self.casts, self.turn_rounds, PerceiveObservation(self.short_term_memories, self.clock)
        )
        self.deliver_perception = DeliverPerception(
            scope,
            ObservationExit(WORLD, day_night, scenario.design.clock_wording, receiver),
            PerceptionReportsReceived(),
        )
        if delivers_world_events:
            distributor.register_receiver(DeliverPerceptionOfCommittedEvents(scenario.design, self.deliver_perception))
        self.episodes = InMemoryEpisodeRepository(handoff=discard_events)
        self.memo_books = InMemoryMemoBookRepository(handoff=discard_events)
        self.visited_places = InMemoryVisitedPlacesRepository()
        self.episode_writer = ScriptedEpisodeWriter()
        self.circumstances = CircumstancesOfBeings(self.beings)
        self.memory_writing.write_with(
            backstory_writer=ScriptedBackstoryWriter(),
            episode_writer=self.episode_writer,
            short_term_memories=self.short_term_memories,
            episodes=self.episodes,
            circumstances=self.circumstances,
        )
        self.end_play = EndPlaySession(
            casts=self.casts,
            leave_environment=LeaveEnvironment(
                writing_in_background=self.memory_writing,
                write_episodes=WriteEpisodesOnLeaving(
                    self.short_term_memories, self.episode_writer, AddEpisodesToMemory(self.episodes)
                ),
                circumstances=self.circumstances,
                turn_reader=self.clock,
            ),
        )

    def beings_taking_turns(
        self,
        completion: ActionChoosingCompletion,
        *,
        closing: str = "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。",
    ) -> BeingsTakingTurnsOneByOne:
        design = _scenario().design
        day_night = design.day_night
        assert isinstance(day_night, DayNightDeclaration)
        settle = SettleWorldConditions(self.scope, design)
        return BeingsTakingTurnsOneByOne(
            world=WORLD,
            casts=self.casts,
            being_tools=OfferedBeingTools(
                inner_thought="inner_thought",
                memo=MEMO_FIELD_NAME,
                episode_recall="episode_recall",
                episode_index_shown=True,
            ),
            closing=Closing(instruction=closing),
            describe_scene=DescribeScene(self.scope, design),
            mark_body_as_shown=MarkBodyAsShown(self.scope),
            offer_choices=OfferActionChoices(self.scope, design),
            tell_time=TellCurrentTime(self.scope, day_night, _scenario().design.clock_wording),
            choose_action=ChooseAction(
                working_memory=CurrentWorkingMemory(
                    beings=self.beings,
                    short_term_memories=self.short_term_memories,
                    acquaintances=self.acquaintances,
                    episodes=self.episodes,
                    memo_books=self.memo_books,
                    visited_places=self.visited_places,
                    episode_index_limit=5,
                ),
                completion=completion,
                short_term_memories=self.short_term_memories,
                turn_clock=self.clock,
                memo_books=self.memo_books,
                episodes=self.episodes,
                visited_places=self.visited_places,
                recall_limit=3,
                writing_in_background=self.memory_writing,
            ),
            take_chosen_action=TakeChosenAction(self.scope, design, settle),
            describe_result=DescribeActionResult(self.scope, design, day_night),
            receive_result=ReceiveActionResult(self.short_term_memories, self.clock),
            end_being_turn=EndBeingTurn(self.short_term_memories, self.clock),
        )

    def play_rounds(self, turn_takers: TurnTakers) -> PlayRounds:
        design = _scenario().design
        return PlayRounds(
            casts=self.casts,
            turn_rounds=self.turn_rounds,
            turn_takers=turn_takers,
            check_readiness=CheckReadinessToAct(self.scope),
            world_has_ended=WorldHasEnded(self.scope),
            accept_time_passage=AcceptWorldTimePassage(
                self.scope, PassWorldTime(self.scope), SettleWorldConditions(self.scope, design)
            ),
        )

    def ended(self) -> None:
        """Being を世界から離し、裏の書き起こしを止める。"""
        try:
            self.end_play(EndPlaySessionCommand(WORLD))
        finally:
            self.memory_writing.shutdown()

    def started(self) -> MineVillageSession:
        self.start(self.command)
        return self


def door_breaks_at(spot: SpotId, *, by: PersonId | None = None) -> SightStimulus:
    actor = {} if by is None else {"actor": by}
    clear = "扉が壊れた" if by is None else "{actor}が扉を壊した"
    return SightStimulus(
        where=spot,
        witness=SightTexts(
            clear=TextWithUnassignedPeople(clear).about(actor),
            dim=TextWithUnassignedPeople("何かが崩れた").about({}),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=() if by is None else (by,),
        salience=Notable(),
        always_delivered=False,
        at=WorldTick(0),
        present=WhoeverIsThere(),
    )
