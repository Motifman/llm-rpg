from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import final

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
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.episode_writer import EpisodeWriter
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
from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee, DomainEvent, EventDispatcher
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
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
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import PerceptionDeliveryReport
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from ai_rpg_world.play_session.application.beings_taking_turns import BeingsTakingTurnsAtOnce, BeingTurnSteps
from ai_rpg_world.play_session.application.end_play_session import EndPlaySession, EndPlaySessionCommand
from ai_rpg_world.play_session.application.hand_observation_to_being import HandObservationToBeing
from ai_rpg_world.play_session.application.handlers.pass_observation_to_being_handler import (
    PassObservationToBeingHandler,
)
from ai_rpg_world.play_session.application.play_rounds import PlayRounds, PlayRoundsCommand, PlayStopped
from ai_rpg_world.play_session.application.start_play_session import StartPlaySession, StartPlaySessionCommand
from ai_rpg_world.play_session.domain.turn_rounds import (
    ObservationPassedOnEvent,
    RoundCount,
    TurnFinishedEvent,
    TurnRoundsEvent,
)
from ai_rpg_world.play_session.infrastructure.in_memory_cast_repository import InMemoryCastRepository
from ai_rpg_world.play_session.infrastructure.in_memory_turn_rounds_repository import InMemoryTurnRoundsRepository
from ai_rpg_world.play_session.infrastructure.roles_from_scenario import casting_by_person_name, roles_from_scenario

_INNER_THOUGHT = "inner_thought"
_EPISODE_RECALL = "episode_recall"
_EPISODE_INDEX_REVISION = "episode_revise_index"


@final
@dataclass(frozen=True)
class GameWorldWriters:
    action_choosing: ActionChoosingCompletion
    episode_writer: EpisodeWriter
    backstory_writer: BackstoryWriter


@final
@dataclass(frozen=True)
class GameWorldPlayResult:
    stopped: PlayStopped
    last_tick: WorldTick
    finished_turns: int
    writing_failures: dict[str, int]


class _PerceptionReportsCounted:
    # 書き出しは #2233 で足す。run のあいだ全部ためると、長い run でメモリが増え続ける
    def __init__(self) -> None:
        self.count = 0

    def receive(self, report: PerceptionDeliveryReport) -> None:
        self.count += 1


def _failed_handing_off(*_: object) -> None:
    # 再送必須で登録したハンドラの失敗は handoff が投げ直すので、ここでは何もしない
    pass


@final
class GameWorldPlay:
    def __init__(
        self,
        *,
        scenario_path: Path,
        scenario: LoadedScenario,
        scenario_hash: str,
        settings: GameWorldPlaySettings,
        writers: GameWorldWriters,
        round_limit: int,
        closing: Closing,
    ) -> None:
        design = scenario.design
        # 時刻の札を作る部品は昼夜を前提にするので、昼夜を宣言しない世界は組み立てる前に断る (D2222)
        day_night = design.day_night_declaration()
        self.world = world = WorldId(f"{scenario_path.stem}#1")
        self._store = SqliteWorldStore.create(
            ":memory:",
            world_id=world,
            scenario=scenario_path.stem,
            scenario_hash=scenario_hash,
            design=design,
            random=SeedableRandomSource(settings.random_seed),
        )
        distributor = CommittedEventsDistributor()
        scope = CommandScope(self._store, distributor)
        self._scope = scope

        beings = InMemoryBeingRepository()
        acquaintances = InMemoryAcquaintanceRepository()
        clock = InMemoryMemoryTurnClock()
        self.memory_writing = MemoryWritingOnThreads(
            wait_limit_seconds=settings.writing_wait_limit_seconds,
            workers=settings.writing_workers,
            max_pending=settings.writing_max_pending,
        )
        short_term_memories = InMemoryShortTermMemoryRepository(handoff=self.memory_writing.handoff)
        episodes = InMemoryEpisodeRepository(handoff=_discard)
        memo_books = InMemoryMemoBookRepository(handoff=_discard)
        visited_places = InMemoryVisitedPlacesRepository()
        circumstances = CircumstancesOfBeings(beings)
        self.memory_writing.write_with(
            backstory_writer=writers.backstory_writer,
            episode_writer=writers.episode_writer,
            short_term_memories=short_term_memories,
            episodes=episodes,
            circumstances=circumstances,
        )

        self.casts = casts = InMemoryCastRepository(handoff=_discard)
        self._finished_turns = 0
        self._turn_round_dispatcher: EventDispatcher[None] = EventDispatcher(failure_observer=_failed_handing_off)
        self._turn_round_dispatcher.register_after_commit(
            ObservationPassedOnEvent,
            PassObservationToBeingHandler(casts, PerceiveObservation(short_term_memories, clock)).handle,
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        self.turn_rounds = turn_rounds = InMemoryTurnRoundsRepository(handoff=self._hand_off_turn_round_events)

        self.perception_reports = _PerceptionReportsCounted()
        deliver_perception = DeliverPerception(
            scope,
            ObservationExit(world, day_night, design.clock_wording, HandObservationToBeing(world, turn_rounds)),
            self.perception_reports,
        )
        distributor.register_receiver(DeliverPerceptionOfCommittedEvents(design, deliver_perception))

        self._start = StartPlaySession(
            open_world=OpenWorld(self._store),
            name_person=NamePerson(scope),
            brief=BriefEnteringPerson(design),
            prepare_being=PrepareBeing(beings),
            enter_environment=EnterEnvironment(beings, acquaintances, clock),
            casts=casts,
            turn_rounds=turn_rounds,
        )
        self._start_command = StartPlaySessionCommand(
            open_world=OpenWorldCommand(world_id=world, design=design),
            environment_name=design.introduction.title.text,
            roles=roles_from_scenario(scenario),
            casting=casting_by_person_name(scenario),
            round_limit=RoundCount(round_limit),
            wake_waiting_after=RoundCount(settings.wake_waiting_after_rounds),
        )
        index_shown = settings.episode_index_enabled
        steps = BeingTurnSteps(
            world=world,
            casts=casts,
            being_tools=OfferedBeingTools(
                inner_thought=_INNER_THOUGHT,
                memo=MEMO_FIELD_NAME if settings.memo_tools_enabled else None,
                episode_recall=_EPISODE_RECALL if index_shown else None,
                episode_index_revision=_EPISODE_INDEX_REVISION if index_shown else None,
                episode_index_shown=index_shown,
            ),
            closing=closing,
            describe_scene=DescribeScene(scope, design),
            mark_body_as_shown=MarkBodyAsShown(scope),
            offer_choices=OfferActionChoices(scope, design),
            tell_time=TellCurrentTime(scope, day_night, design.clock_wording),
            choose_action=ChooseAction(
                working_memory=CurrentWorkingMemory(
                    beings=beings,
                    short_term_memories=short_term_memories,
                    acquaintances=acquaintances,
                    episodes=episodes,
                    memo_books=memo_books,
                    visited_places=visited_places,
                    episode_index_limit=settings.episode_index_limit,
                ),
                completion=writers.action_choosing,
                short_term_memories=short_term_memories,
                turn_clock=clock,
                memo_books=memo_books,
                episodes=episodes,
                visited_places=visited_places,
                recall_limit=settings.episode_recall_max_handles,
                writing_in_background=self.memory_writing,
            ),
            take_chosen_action=TakeChosenAction(scope, design, SettleWorldConditions(scope, design)),
            describe_result=DescribeActionResult(scope, design, day_night),
            receive_result=ReceiveActionResult(short_term_memories, clock),
            end_being_turn=EndBeingTurn(short_term_memories, clock),
        )
        self._play_rounds = PlayRounds(
            casts=casts,
            turn_rounds=turn_rounds,
            turn_takers=BeingsTakingTurnsAtOnce(steps, turn_rounds),
            check_readiness=CheckReadinessToAct(scope),
            world_has_ended=WorldHasEnded(scope),
            accept_time_passage=AcceptWorldTimePassage(
                scope, PassWorldTime(scope), SettleWorldConditions(scope, design)
            ),
        )
        self._end_play = EndPlaySession(
            casts=casts,
            leave_environment=LeaveEnvironment(
                writing_in_background=self.memory_writing,
                write_episodes=WriteEpisodesOnLeaving(
                    short_term_memories, writers.episode_writer, AddEpisodesToMemory(episodes)
                ),
                circumstances=circumstances,
                turn_reader=clock,
            ),
        )

    def play(self) -> GameWorldPlayResult:
        try:
            self._start(self._start_command)
            stopped = self._play_rounds(PlayRoundsCommand(self.world))
            self._end_play(EndPlaySessionCommand(self.world))
            last_tick = self._scope.run(lambda session: session.facts().now())
        finally:
            # 書き終わった書き起こしを捨てないよう、例外で抜けても止める
            self.memory_writing.shutdown()
            self._store.close()
        return GameWorldPlayResult(
            stopped=stopped,
            last_tick=last_tick,
            finished_turns=self._finished_turns,
            writing_failures=self.memory_writing.failures(),
        )

    def _hand_off_turn_round_events(self, events: Sequence[TurnRoundsEvent]) -> None:
        self._finished_turns += sum(1 for event in events if isinstance(event, TurnFinishedEvent))
        self._turn_round_dispatcher.handoff(events)


def _discard(events: Sequence[DomainEvent]) -> None:
    pass
