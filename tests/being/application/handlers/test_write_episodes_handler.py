from __future__ import annotations

from collections.abc import Iterator

from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory, AddEpisodesToMemoryCommand
from ai_rpg_world.being.application.handlers.write_episodes_handler import (
    EpisodeWritingCircumstances,
    WriteEpisodesHandler,
)
from ai_rpg_world.being.application.write_episodes import WriteEpisodesCommand
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemory, ShortTermMemoryRangeFilledEvent
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.eventing import AsyncEventHandler
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being_p1")
CONTENTS = EpisodeContents(
    contents=(
        EpisodeContent(index=EpisodeIndex(summary="鐘の記憶", recall_when="鐘の話が出たとき"), body="鐘が鳴った。"),
    )
)


def _seen(body: str) -> Observation:
    return Observation(
        body=body,
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


def _ids() -> Iterator[str]:
    n = 0
    while True:
        n += 1
        yield f"3f2a7b9c-1d2e-4f00-8a00-{n:012d}"


class _Writer(EpisodeWriter):
    def __init__(self) -> None:
        self.calls = 0

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        self.calls += 1
        return CONTENTS


def _range_filled() -> ShortTermMemoryRangeFilledEvent:
    memory = ShortTermMemory.empty(ADA)
    for turn in range(0, 20):
        memory.perceive(_seen(f"ターン {turn + 1} の出来事"), current_turn=turn)
    memory.end_turn(turn=20)
    (event,) = memory.get_events()
    assert isinstance(event, ShortTermMemoryRangeFilledEvent)
    return event


class _World:
    def __init__(self) -> None:
        self.episodes = InMemoryEpisodeRepository(handoff=discard_events)
        self.writer = _Writer()
        self.looked_up: list[BeingId] = []
        self.persona_looked_up: list[BeingId] = []
        ids = _ids()
        self.handler = WriteEpisodesHandler(
            writer=self.writer,
            add_episodes=AddEpisodesToMemory(self.episodes, new_episode_id=lambda: next(ids)),
            persona_of=lambda being_id: (
                self.persona_looked_up.append(being_id),
                Persona(name="エイダ", first_person="わたし"),
            )[1],
            circumstances_of=lambda being_id: (
                self.looked_up.append(being_id),
                EpisodeWritingCircumstances(persona_text="慎重", environment_name="廃坑の山村"),
            )[1],
        )


class TestWriteEpisodesHandler:
    """WriteEpisodesHandler が、範囲が埋まったイベントからエピソードを書き、その Being の記憶に加えることを保証する。"""

    def test_prepare_builds_a_write_command_with_the_circumstances(self) -> None:
        """prepare は、Being の保存先から引いた人柄、ゲームの側の関数で引いた人格の文といる環境、まとめる出来事、埋まったターンを持つ WriteEpisodesCommand を作る。"""
        world = _World()
        event = _range_filled()

        command = world.handler.prepare(event)

        assert command == WriteEpisodesCommand(
            being_id=ADA,
            persona=Persona(name="エイダ", first_person="わたし"),
            persona_text="慎重",
            experiences=event.experiences,
            environment_name="廃坑の山村",
            written_turn=20,
        )
        assert (world.persona_looked_up, world.looked_up) == ([ADA], [ADA])

    def test_handle_writes_and_returns_a_command_to_add_the_episodes(self) -> None:
        """handle はエピソードの中身を書き、環境と書いたターンとともに記憶に加える AddEpisodesToMemoryCommand を返す。記憶はまだ変えない。"""
        world = _World()

        command = world.handler.handle(world.handler.prepare(_range_filled()))

        assert command == AddEpisodesToMemoryCommand(
            being_id=ADA, contents=CONTENTS, environment_name="廃坑の山村", written_turn=20
        )
        assert world.episodes.list_by_being(ADA) == ()

    def test_apply_adds_the_episodes_to_the_memory(self) -> None:
        """apply は、書いた中身をエピソードとしてその Being の記憶に加える。"""
        world = _World()

        world.handler.apply(
            AddEpisodesToMemoryCommand(being_id=ADA, contents=CONTENTS, environment_name="廃坑の山村", written_turn=20)
        )

        (episode,) = world.episodes.list_by_being(ADA)
        assert (episode.index.summary, episode.environment_name, episode.written_turn) == ("鐘の記憶", "廃坑の山村", 20)

    def test_handler_is_an_async_event_handler(self) -> None:
        """イベント基盤の非同期のハンドラの基底を継ぐ (design_decisions D1824-15)。"""
        assert isinstance(_World().handler, AsyncEventHandler)
