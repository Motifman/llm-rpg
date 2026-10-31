from __future__ import annotations

from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.application.write_episodes_on_leaving import (
    WriteEpisodesOnLeaving,
    WriteEpisodesOnLeavingCommand,
)
from ai_rpg_world.being.contract import UNKNOWN, AgentMove, Observation, ObservedTime, OwnActionResult, SeenOrHeard
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import ObservedOutcome, ShortTermMemory
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being_p1")
CONTENTS = EpisodeContents(
    contents=(
        EpisodeContent(index=EpisodeIndex(summary="鐘の記憶", recall_when="鐘の話が出たとき"), body="鐘が鳴った。"),
    )
)


def _observation(body: str, *, own_call_id: str | None = None) -> Observation:
    own = own_call_id is not None
    return Observation(
        body=body,
        route=OwnActionResult(call_id=own_call_id, succeeded=True) if own else SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=own,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


class _Writer(EpisodeWriter):
    def __init__(self) -> None:
        self.events_texts: list[str] = []

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        self.events_texts.append(events_text)
        return CONTENTS


def _remembered_turns(last_turn: int) -> InMemoryShortTermMemoryRepository:
    """ターンごとに「ターン N の出来事」を 1 つ見た短期記憶を保存する。"""
    store = InMemoryShortTermMemoryRepository(handoff=discard_events)
    memory = ShortTermMemory.empty(ADA)
    for turn in range(1, last_turn + 1):
        memory.perceive(_observation(f"ターン {turn} の出来事"), current_turn=turn - 1)
    store.save(memory)
    return store


def _command() -> WriteEpisodesOnLeavingCommand:
    return WriteEpisodesOnLeavingCommand(
        being_id=ADA,
        persona=Persona(name="エイダ"),
        persona_text="慎重",
        environment_name="廃坑の山村",
        written_turn=25,
    )


class TestWriteEpisodesOnLeaving:
    """WriteEpisodesOnLeaving が、範囲が埋まったときにまとめていない出来事からエピソードを書き、記憶に加えることを保証する (design_decisions D1824-23)。"""

    def test_writes_from_experiences_after_the_awaited_range_and_adds_them(self) -> None:
        """範囲 (ターン 10 まで) のいきさつを待っているとき、書き手にはターン 11 から 21 の出来事だけを渡し、書いた中身を環境と書いたターンを付けて記憶に加える。"""
        store = _remembered_turns(21)
        memory = store.get(ADA)
        memory.end_turn(turn=20)
        store.save(memory)
        writer = _Writer()
        episodes = InMemoryEpisodeRepository(handoff=discard_events)

        outcome = WriteEpisodesOnLeaving(store, writer, AddEpisodesToMemory(episodes)).execute(_command())

        (events_text,) = writer.events_texts
        assert events_text.splitlines() == [f"- [1日目 朝] ターン {turn} の出来事" for turn in range(11, 22)]
        assert (outcome.experience_count, outcome.awaited_until_turn) == (11, 10)
        assert outcome.result is not None
        (written,) = episodes.list_by_being(ADA)
        assert (written.environment_name, written.written_turn, written.index.summary) == ("廃坑の山村", 25, "鐘の記憶")

    def test_nothing_to_write_does_not_call_the_writer(self) -> None:
        """まとめていない出来事が行にならない (結果を待っている 1 手だけの) ときは、書き手を呼ばず、結果は無しで出来事の数だけ返す。"""
        store = InMemoryShortTermMemoryRepository(handoff=discard_events)
        memory = ShortTermMemory.empty(ADA)
        memory.act(AgentMove(call_id="call-1", tool_name="wait", arguments={}), current_turn=1)
        store.save(memory)
        writer = _Writer()

        outcome = WriteEpisodesOnLeaving(
            store, writer, AddEpisodesToMemory(InMemoryEpisodeRepository(handoff=discard_events))
        ).execute(_command())

        assert writer.events_texts == []
        assert (outcome.experience_count, outcome.result) == (1, None)

    def test_awaited_until_turn_is_none_when_no_backstory_is_awaited(self) -> None:
        """いきさつを待っていなければ、awaited_until_turn は None になる。"""
        store = _remembered_turns(3)

        outcome = WriteEpisodesOnLeaving(
            store, _Writer(), AddEpisodesToMemory(InMemoryEpisodeRepository(handoff=discard_events))
        ).execute(_command())

        assert outcome.awaited_until_turn is None

    def test_short_term_memory_is_not_changed(self) -> None:
        """書いても、短期記憶の出来事は外さない。"""
        store = _remembered_turns(3)
        before = store.get(ADA).experiences

        WriteEpisodesOnLeaving(
            store, _Writer(), AddEpisodesToMemory(InMemoryEpisodeRepository(handoff=discard_events))
        ).execute(_command())

        assert store.get(ADA).experiences == before

    def test_answered_move_is_written_with_its_result(self) -> None:
        """結果の来た 1 手は、結果の行として書き手に渡る。"""
        store = InMemoryShortTermMemoryRepository(handoff=discard_events)
        memory = ShortTermMemory.empty(ADA)
        memory.act(AgentMove(call_id="call-1", tool_name="wait", arguments={}), current_turn=1)
        memory.receive_result(ObservedOutcome(_observation("待った", own_call_id="call-1")), current_turn=1)
        store.save(memory)
        writer = _Writer()

        WriteEpisodesOnLeaving(
            store, writer, AddEpisodesToMemory(InMemoryEpisodeRepository(handoff=discard_events))
        ).execute(_command())

        assert writer.events_texts == ["- [1日目 朝] 待った"]
