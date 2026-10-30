from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.being.being_backstory_writing import BeingBackstoryWriting, WrittenBackstory
from ai_rpg_world.application.llm.services.stub_backstory_completion import stub_backstory_completion
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.short_term_memory import (
    Backstory,
    Experience,
    FoldRequested,
    StaleBackstoryDiscarded,
)
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_p1")


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


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


class _Writer(BackstoryWriter):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write(
        self,
        *,
        self_name: str,
        persona: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> Backstory:
        self.calls.append(
            {"self_name": self_name, "persona": persona, "experiences": experiences, "previous": previous}
        )
        return Backstory(flow=f"{len(experiences)} 件の流れ", mood="", written_turn=written_turn, until_turn=until_turn)


class _World:
    def __init__(self) -> None:
        self.handed: list[object] = []
        self.store = InMemoryShortTermMemoryRepository(handoff=self.handed.extend)
        self.writer = _Writer()
        self.recorder: _Recorder | None = _Recorder()
        self.writing = BeingBackstoryWriting(
            writer=self.writer,
            store=self.store,
            persona_of=lambda being_id: ("エイダ", "慎重"),
            trace_recorder_provider=lambda: self.recorder,
            current_tick_provider=lambda: 7,
        )

    def _noted(self, event: FoldRequested) -> FoldRequested:
        self.writing.note_person(event)
        return event

    def request(self, *, previous: Backstory | None = None) -> FoldRequested:
        """ターン 1 から 20 に 1 つずつ観測を置き、ターン 20 でいきさつを頼んで保存する。頼みごとのイベントを返す。"""
        memory = self.store.get(ADA)
        if previous is not None:
            memory.add_backstory(previous)
        for turn in range(0, 20):
            memory.perceive(_seen(f"ターン {turn + 1} の出来事"), current_turn=turn)
        memory.fold(current_turn=20)
        self.store.save(memory)
        (event,) = [e for e in self.handed if isinstance(e, FoldRequested)]
        self.handed.clear()
        return event


class TestNotePerson:
    """BeingBackstoryWriting.note_person が、裏のスレッドが Being の保存先を引かずに済むよう、本人の名前と性格を先に引いておくことを保証する。"""

    def test_person_is_looked_up_once_and_write_does_not_look_it_up(self) -> None:
        """名前と性格は Being ごとに 1 度だけ引く。write は先に引いた名前と性格を書き手に渡し、引き直さない。"""
        world = _World()
        looked_up: list[BeingId] = []
        world.writing._persona_of = lambda being_id: (looked_up.append(being_id), ("エイダ", "慎重"))[1]  # type: ignore[method-assign]
        event = world.request()
        world.writing.note_person(event)
        world.writing.note_person(event)

        world.writing.write(event)

        assert looked_up == [ADA]
        assert (world.writer.calls[0]["self_name"], world.writer.calls[0]["persona"]) == ("エイダ", "慎重")


class TestWrite:
    """BeingBackstoryWriting.write が、頼まれた範囲と前のいきさつと本人の人物像で、いきさつを作ることを保証する。"""

    def test_writes_from_the_requested_experiences_and_the_latest_backstory(self) -> None:
        """頼まれた範囲の出来事 (ターン 1 から 10 の 10 件)、いちばん新しいいきさつ、本人の名前と性格を書き手に渡し、その Being のいきさつとして返す。短期記憶はまだ変えない。"""
        world = _World()
        previous = Backstory(flow="前の流れ", mood="", written_turn=0, until_turn=0)
        event = world.request(previous=previous)

        written = world.writing.write(world._noted(event))

        (call,) = world.writer.calls
        assert (call["self_name"], call["persona"], len(call["experiences"]), call["previous"]) == (
            "エイダ",
            "慎重",
            10,
            previous,
        )
        assert written == WrittenBackstory(
            being_id=ADA, backstory=Backstory(flow="10 件の流れ", mood="", written_turn=20, until_turn=10)
        )
        assert world.store.get(ADA).request is not None

    def test_writer_failure_propagates(self) -> None:
        """書き手が失敗すると、例外をそのまま投げる。非同期の配送が失敗として trace に残し、頼みごとは残る。"""
        world = _World()
        event = world.request()

        def broken(**kwargs: Any) -> Backstory:
            raise ValueError("LLM が答えなかった")

        world.writer.write = broken  # type: ignore[method-assign]

        with pytest.raises(ValueError):
            world.writing.write(world._noted(event))


class TestApply:
    """BeingBackstoryWriting.apply が、作ったいきさつを短期記憶に入れて保存し、trace に残すことを保証する。"""

    def test_backstory_is_added_and_covered_experiences_are_dropped(self) -> None:
        """いきさつを入れると、ターン 10 までの出来事が外れ、頼みごとが済み、being_backstory_written が残る。"""
        world = _World()
        written = world.writing.write(world._noted(world.request()))

        world.writing.apply(written)

        memory = world.store.get(ADA)
        assert ([b.until_turn for b in memory.backstories], memory.recent_from, memory.request) == ([10], 11, None)
        ((kind, payload),) = world.recorder.events  # type: ignore[union-attr]
        assert kind == TraceEventKind.BEING_BACKSTORY_WRITTEN
        assert (payload["being_id"], payload["until_turn"], payload["written_turn"], payload["flow"]) == (
            "being_p1",
            10,
            20,
            "10 件の流れ",
        )

    def test_late_backstory_for_the_same_range_is_discarded_through_the_store(self) -> None:
        """同じ範囲のいきさつが 2 度届くと、2 度目は入らず、保存するときに StaleBackstoryDiscarded が配り手に渡る。"""
        world = _World()
        written = world.writing.write(world._noted(world.request()))
        world.writing.apply(written)

        world.writing.apply(written)

        assert [type(e) for e in world.handed] == [StaleBackstoryDiscarded]
        assert len(world.store.get(ADA).backstories) == 1

    def test_apply_without_recorder_still_adds_the_backstory(self) -> None:
        """trace recorder の無い run でも、いきさつは入る。"""
        world = _World()
        world.recorder = None
        written = world.writing.write(world._noted(world.request()))

        world.writing.apply(written)

        assert len(world.store.get(ADA).backstories) == 1


class TestStubCompletion:
    """実 LLM を呼ばない run のスタブが、まとめる範囲の最初の出来事を流れにすることを保証する。"""

    def test_first_event_becomes_the_flow(self) -> None:
        """最初の「- 」で始まる行を、(スタブ) を付けた流れにして返す。"""
        response = stub_backstory_completion(
            [
                {"role": "system", "content": "指示"},
                {"role": "user", "content": "あなた = エイダ\n- [1日目 朝] 鐘が鳴った\n- [1日目 朝] 扉が開いた"},
            ]
        )

        assert response == {"compressed_activity": "(スタブ) [1日目 朝] 鐘が鳴った", "emotional_summary": ""}
