from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.application.leave_environment import EnvironmentLeft, LeaveEnvironment, LeaveEnvironmentCommand
from ai_rpg_world.being.application.memory_writing_in_background import MemoryWritingInBackground
from ai_rpg_world.being.application.write_episodes_on_leaving import WriteEpisodesOnLeaving
from ai_rpg_world.being.application.writing_circumstances import CircumstancesOfBeings
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode_writer import EpisodeContents
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemory
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from tests.event_handoff_helpers import discard_events

GEN = BeingId("gen")


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


class _Background(MemoryWritingInBackground):
    """待つよう頼まれた順を ``steps`` に残し、決めた答えを返す。"""

    def __init__(self, steps: list[str], *, finished: bool) -> None:
        self._steps = steps
        self._finished = finished

    def take_in_finished(self, being_id: BeingId) -> None:
        raise AssertionError("離れるときは書きかけを待つ")

    def finish(self, being_id: BeingId) -> bool:
        self._steps.append(f"finish {being_id.value}")
        return self._finished


class _RecordingWriter(ScriptedEpisodeWriter):
    def __init__(self, steps: list[str]) -> None:
        super().__init__()
        self._steps = steps

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        self._steps.append("write")
        return super().write(persona=persona, persona_text=persona_text, events_text=events_text)


@dataclass(frozen=True)
class _Leaving:
    steps: list[str]
    writer: _RecordingWriter
    episodes: InMemoryEpisodeRepository
    left: EnvironmentLeft


def _leave(*, finished: bool) -> _Leaving:
    steps: list[str] = []
    beings = InMemoryBeingRepository()
    beings.add_if_absent(
        Being(
            being_id=GEN,
            persona=Persona(name="ゲン"),
            attachment=BeingAttachment(environment_id="mine#1", environment_name="廃坑の山村"),
        )
    )
    memories = InMemoryShortTermMemoryRepository(handoff=discard_events)
    memory = ShortTermMemory.empty(GEN)
    memory.perceive(_seen("鐘が鳴った"), current_turn=2)
    memories.save(memory)
    clock = InMemoryMemoryTurnClock()
    clock.replace_all_by_being(GEN, turn=3)
    writer = _RecordingWriter(steps)
    episodes = InMemoryEpisodeRepository(handoff=discard_events)
    left = LeaveEnvironment(
        writing_in_background=_Background(steps, finished=finished),
        write_episodes=WriteEpisodesOnLeaving(memories, writer, AddEpisodesToMemory(episodes)),
        circumstances=CircumstancesOfBeings(beings),
        turn_reader=clock,
    ).execute(LeaveEnvironmentCommand(GEN))
    return _Leaving(steps, writer, episodes, left)


class TestLeaveEnvironment:
    """LeaveEnvironment が、裏の書き起こしを待ってから、まだまとめていない出来事をエピソードにすることを保証する。"""

    def test_waits_for_the_background_before_writing_the_rest(self) -> None:
        """離れるときは、裏の書き起こしを待ってから残りを書く。待たずに書くと、裏で書いた範囲と残りの境目がずれる。"""
        assert _leave(finished=True).steps == ["finish gen", "write"]

    def test_rest_is_written_as_the_being_in_the_environment_at_the_current_turn(self) -> None:
        """残りの出来事は、ゲンの【ペルソナ】の文で書き、廃坑の山村のエピソードとして記憶の時計のターン 3 で残る。"""
        leaving = _leave(finished=True)

        [(persona_text, events_text)] = leaving.writer.written
        assert persona_text == "あなたはゲン。" and "鐘が鳴った" in events_text
        [episode] = leaving.episodes.list_by_being(GEN)
        assert (episode.environment_name, episode.written_turn) == ("廃坑の山村", 3)

    def test_unfinished_background_is_reported(self) -> None:
        """上限の時間までに裏の書き起こしが終わらなければ、残りは書いたうえで、終わらなかったことを返す。"""
        leaving = _leave(finished=False)

        assert leaving.left.background_finished is False
        assert len(leaving.episodes.list_by_being(GEN)) == 1
