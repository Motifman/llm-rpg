from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ai_rpg_world.application.being.being_episode_writing import (
    BeingEpisodeWriting,
    WriterCircumstances,
    WrittenEpisodeContents,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.contract import UNKNOWN, AgentMove, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.short_term_memory import FoldRequested, ShortTermMemory
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_p1")


def _seen(body: str) -> Observation:
    return Observation(body=body, route=SeenOrHeard(), time=ObservedTime(display="1日目 朝"), subject_is_self=False, subject_name=UNKNOWN, source=UNKNOWN, place=UNKNOWN, addressed_to_self=UNKNOWN)


def _ids() -> Iterator[str]:
    n = 0
    while True:
        n += 1
        yield f"3f2a7b9c-1d2e-4f00-8a00-{n:012d}"


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


class _Writer(EpisodeWriter):
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def write(self, *, self_name: str, persona: str, events_text: str) -> EpisodeContents:
        self.calls.append({"self_name": self_name, "persona": persona, "events_text": events_text})
        content = EpisodeContent(index=EpisodeIndex(summary="鐘の記憶", recall_when="鐘の話が出たとき"), body="鐘が鳴っていた。", truncated={"body": 401})
        return EpisodeContents(contents=(content,), dropped_count=1)


class _World:
    def __init__(self) -> None:
        self.episodes = InMemoryEpisodeRepository()
        self.writer = _Writer()
        self.recorder: _Recorder | None = _Recorder()
        self.environment = "廃坑の山村"
        ids = _ids()
        self.writing = BeingEpisodeWriting(
            writer=self.writer,
            add_episodes=AddEpisodesToMemory(self.episodes, new_episode_id=lambda: next(ids)),
            circumstances_of=lambda being_id: WriterCircumstances(self_name="エイダ", persona="慎重", environment_name=self.environment),
            trace_recorder_provider=lambda: self.recorder,
            current_tick_provider=lambda: 7,
        )

    @staticmethod
    def request(*, seen: bool = True) -> FoldRequested:
        """ターン 20 まで 1 つずつ出来事を置き、ターン 20 で頼んだときの FoldRequested を返す。seen が偽なら、出来事は結果の来ない 1 手だけにする。"""
        memory = ShortTermMemory.empty(ADA)
        for turn in range(0, 20):
            if seen:
                memory.perceive(_seen(f"ターン {turn + 1} の出来事"), current_turn=turn)
            elif turn > 0:
                memory.act(AgentMove(call_id=f"call-{turn}", tool_name="interact", arguments={}), current_turn=turn)
        memory.fold(current_turn=20)
        (event,) = [e for e in memory.get_events() if isinstance(e, FoldRequested)]
        return event

    def written(self, request: FoldRequested) -> WrittenEpisodeContents:
        self.writing.note(request)
        return self.writing.write(request)


class TestWrite:
    """BeingEpisodeWriting.write が、頼まれた範囲の出来事と本人の名前・性格・環境で中身を書き、記憶には触らないことを保証する。"""

    def test_writes_from_the_requested_experiences_and_the_noted_circumstances(self) -> None:
        """頼まれた範囲の出来事 (古い 10 件) を【直近の出来事】と同じ行にして渡し、名前と性格を添える。環境と頼んだターンを結果に持ち、まだ記憶に加えない。"""
        world = _World()

        written = world.written(world.request())

        (call,) = world.writer.calls
        assert (call["self_name"], call["persona"]) == ("エイダ", "慎重")
        assert call["events_text"].splitlines()[0] == "- [1日目 朝] ターン 1 の出来事"
        assert len(call["events_text"].splitlines()) == 10
        assert (written.environment_name, written.written_turn, written.event_count) == ("廃坑の山村", 20, 10)
        assert world.episodes.list_by_being(ADA) == ()

    def test_circumstances_are_noted_per_request(self) -> None:
        """環境は頼みごとごとに引く。先に頼んだものは、頼んだときの環境で書く。"""
        world = _World()
        first, second = world.request(), world.request()
        world.writing.note(first)
        world.environment = "港町"
        world.writing.note(second)

        assert (world.writing.write(first).environment_name, world.writing.write(second).environment_name) == ("廃坑の山村", "港町")

    def test_range_without_lines_is_not_written(self) -> None:
        """範囲の出来事が、結果の来ない 1 手だけで行にならなければ、書き手を呼ばず、中身を持たない。"""
        world = _World()

        written = world.written(world.request(seen=False))

        assert (world.writer.calls, written.contents) == ([], None)

    def test_writer_failure_propagates(self) -> None:
        """書き手が失敗すると、例外をそのまま投げる。非同期の配送が失敗として trace に残す。"""
        world = _World()

        def broken(**kwargs: Any) -> EpisodeContents:
            raise ValueError("LLM が答えなかった")

        world.writer.write = broken  # type: ignore[method-assign]

        with pytest.raises(ValueError):
            world.written(world.request())


class TestApply:
    """BeingEpisodeWriting.apply が、書いた中身をエピソードとして記憶に加え、trace に残すことを保証する。"""

    def test_contents_are_added_and_traced(self) -> None:
        """中身をエピソードとして記憶に加え、episode_writing を trigger=fold、outcome=written で、エピソードの目次と切り詰めと捨てた数とともに残す。"""
        world = _World()

        world.writing.apply(world.written(world.request()))

        (episode,) = world.episodes.list_by_being(ADA)
        assert (episode.index.summary, episode.environment_name, episode.written_turn) == ("鐘の記憶", "廃坑の山村", 20)
        ((kind, player_id, payload),) = world.recorder.events  # type: ignore[union-attr]
        assert (kind, player_id) == (TraceEventKind.EPISODE_WRITING, None)
        assert {k: payload[k] for k in ("trigger", "being_id", "outcome", "event_count", "episode_count", "dropped_count")} == {
            "trigger": "fold", "being_id": "being_p1", "outcome": "written", "event_count": 10, "episode_count": 1, "dropped_count": 1,
        }
        assert payload["episodes"] == [{"handle": episode.handle, "summary": "鐘の記憶", "recall_when": "鐘の話が出たとき", "body_length": 8, "truncated": {"body": 401}}]

    def test_range_without_lines_is_traced_as_skipped(self) -> None:
        """書かなかった範囲は何も加えず、outcome=skipped、skip_reason=no_events を残す。"""
        world = _World()

        world.writing.apply(world.written(world.request(seen=False)))

        assert world.episodes.list_by_being(ADA) == ()
        ((_, _, payload),) = world.recorder.events  # type: ignore[union-attr]
        assert (payload["outcome"], payload["skip_reason"]) == ("skipped", "no_events")

    def test_apply_without_recorder_still_adds_the_episodes(self) -> None:
        """trace recorder の無い run でも、エピソードは記憶に加わる。"""
        world = _World()
        world.recorder = None

        world.writing.apply(world.written(world.request()))

        assert len(world.episodes.list_by_being(ADA)) == 1


class TestNote:
    """BeingEpisodeWriting.note が引けなかったとき、write が元の原因を指して失敗することを保証する。"""

    def test_write_without_note_says_it_was_not_noted(self) -> None:
        """note が名前と性格と環境を覚えていない頼みごとを write すると、書き手を呼ばず、覚えていないことを LookupError で知らせる。"""
        world = _World()

        with pytest.raises(LookupError, match="not noted"):
            world.writing.write(world.request())

        assert world.writer.calls == []
