from __future__ import annotations

import math
from threading import Event
from time import monotonic, sleep

import pytest

from ai_rpg_world.being.application.end_being_turn import EndBeingTurn, EndBeingTurnCommand
from ai_rpg_world.being.application.writing_circumstances import CircumstancesOfBeings
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode_writer import EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.being.infrastructure.memory_writing_on_threads import MemoryWritingOnThreads
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
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


class _FailingWriter(EpisodeWriter):
    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        raise TimeoutError("no reply in 95 seconds")


class _BlockedWriter(ScriptedEpisodeWriter):
    def __init__(self, release: Event) -> None:
        super().__init__()
        self._release = release

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        assert self._release.wait(2)
        return super().write(persona=persona, persona_text=persona_text, events_text=events_text)


class _Gen:
    """20 ターンぶん出来事を見て、範囲が埋まったところでターンを終えるゲン。"""

    def __init__(
        self, episode_writer: EpisodeWriter, *, wait_limit_seconds: float = 2.0, attached: bool = True
    ) -> None:
        beings = InMemoryBeingRepository()
        beings.add_if_absent(
            Being(
                being_id=GEN,
                persona=Persona(name="ゲン"),
                attachment=BeingAttachment(environment_id="mine#1", environment_name="廃坑の山村")
                if attached
                else None,
            )
        )
        self.writing = MemoryWritingOnThreads(wait_limit_seconds=wait_limit_seconds)
        self.memories = InMemoryShortTermMemoryRepository(handoff=self.writing.handoff)
        self.episodes = InMemoryEpisodeRepository(handoff=discard_events)
        self.backstory_writer = ScriptedBackstoryWriter()
        self.writing.write_with(
            backstory_writer=self.backstory_writer,
            episode_writer=episode_writer,
            short_term_memories=self.memories,
            episodes=self.episodes,
            circumstances=CircumstancesOfBeings(beings),
        )
        memory = self.memories.get(GEN)
        for turn in range(20):
            memory.perceive(_seen(f"ターン {turn + 1} の出来事"), current_turn=turn)
        self.memories.save(memory)
        clock = InMemoryMemoryTurnClock()
        clock.replace_all_by_being(GEN, turn=20)
        self.end_turn = EndBeingTurn(self.memories, clock)


class TestMemoryWritingOnThreads:
    """MemoryWritingOnThreads が、範囲が埋まったいきさつとエピソードを裏で書き、頼まれたときに記憶に入れることを保証する。"""

    def test_filled_range_is_written_and_taken_in_when_finishing(self) -> None:
        """ターン 20 で範囲が埋まると、裏でターン 10 までのいきさつとエピソードを書き、待って入れると両方が記憶にある。"""
        gen = _Gen(ScriptedEpisodeWriter())
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))

            assert gen.writing.finish(GEN) is True

            [backstory] = gen.memories.get(GEN).backstories
            assert (backstory.until_turn, gen.backstory_writer.written) == (10, [10])
            [episode] = gen.episodes.list_by_being(GEN)
            assert episode.environment_name == "廃坑の山村" and "ターン 10 の出来事" in episode.body
            assert gen.writing.failures() == {}
        finally:
            gen.writing.shutdown()

    def test_taking_in_without_waiting_brings_only_what_has_finished(self) -> None:
        """書きかけのあいだに入れるよう頼んでも何も入らず、書き終わったあとに頼むと入る。行動を選ぶ入口は待たない。"""
        release = Event()
        gen = _Gen(_BlockedWriter(release))
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))
            gen.writing.take_in_finished(GEN)
            assert gen.episodes.list_by_being(GEN) == ()

            release.set()
            deadline = monotonic() + 2
            while not gen.episodes.list_by_being(GEN) and monotonic() < deadline:
                gen.writing.take_in_finished(GEN)
                sleep(0.01)

            assert len(gen.episodes.list_by_being(GEN)) == 1
        finally:
            release.set()
            gen.writing.shutdown()

    def test_failed_writer_is_counted_and_finishing_still_returns(self) -> None:
        """エピソードの書き手が落ちると、いきさつは入り、エピソードは入らず、落ちた数が理由ごとに残る。"""
        gen = _Gen(_FailingWriter())
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))

            assert gen.writing.finish(GEN) is True

            assert len(gen.memories.get(GEN).backstories) == 1
            assert gen.episodes.list_by_being(GEN) == ()
            assert gen.writing.failures() == {"handler_failed": 1}
        finally:
            gen.writing.shutdown()

    def test_writing_past_the_wait_limit_is_reported(self) -> None:
        """書き手が上限の時間を過ぎても返らなければ、待つのをやめて False を返し、待ちきれなかったことを数える。"""
        release = Event()
        gen = _Gen(_BlockedWriter(release), wait_limit_seconds=0.05)
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))

            assert gen.writing.finish(GEN) is False
            assert gen.writing.failures() == {"wait_limit_passed": 1}
        finally:
            release.set()
            gen.writing.shutdown()

    def test_writing_finished_after_the_wait_limit_is_taken_in_on_shutdown(self) -> None:
        """待ちきれなかった書き起こしも、止めるまでに書き終われば記憶に入る。書いたエピソードを捨てない。"""
        release = Event()
        gen = _Gen(_BlockedWriter(release), wait_limit_seconds=0.05)
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))
            assert gen.writing.finish(GEN) is False
            release.set()
        finally:
            release.set()
            gen.writing.shutdown()

        assert len(gen.episodes.list_by_being(GEN)) == 1

    def test_taking_in_brings_only_the_asking_beings_writing(self) -> None:
        """ゲンの書き起こしが書き終わっていても、別の Being が入れるよう頼んだときには入らない。"""
        gen = _Gen(ScriptedEpisodeWriter())
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))
            assert gen.writing.finish(BeingId("sayo")) is True
            gen.writing.take_in_finished(BeingId("sayo"))
            assert gen.episodes.list_by_being(GEN) == ()

            assert gen.writing.finish(GEN) is True
            assert len(gen.episodes.list_by_being(GEN)) == 1
        finally:
            gen.writing.shutdown()

    def test_being_outside_any_environment_is_counted_as_not_prepared(self) -> None:
        """どの環境にもいない Being の範囲が埋まると、書き起こしの材料を用意できず、いきさつもエピソードも書かずに数える。"""
        gen = _Gen(ScriptedEpisodeWriter(), attached=False)
        try:
            gen.end_turn.execute(EndBeingTurnCommand(GEN))
            assert gen.writing.finish(GEN) is True

            assert gen.episodes.list_by_being(GEN) == ()
            assert gen.writing.failures() == {"prepare_failed": 2}
        finally:
            gen.writing.shutdown()

    @pytest.mark.parametrize("limit", [-1.0, math.inf, math.nan])
    def test_wait_limit_must_be_a_finite_number_not_below_zero(self, limit: float) -> None:
        """待つ上限が負・無限・数でないときは、組み立てのときに ValueError で断る。環境を離れるときまで気づかないことを避ける。"""
        with pytest.raises(ValueError):
            MemoryWritingOnThreads(wait_limit_seconds=limit)
