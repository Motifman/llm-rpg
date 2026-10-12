"""予期の出来事を、保存のあとで受け取る側へ配り、配れなかった出来事を配り直す挙動を保証する。"""

from __future__ import annotations

from typing import Any

import pytest
from tests.trace_helpers import RecordingTraceRecorder

from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventDispatcher,
    ExpectationEventReceiver,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
    ExpectationSettled,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

RIO = BeingId("being-rio")


class _BeliefMaterialReceiver(ExpectationEventReceiver):
    """確定を信念への材料として積む試験用の受け取る側。受け取り済みの ID を覚えて、二度目は積まない。"""

    def __init__(self) -> None:
        self.materials: list[ExpectationEvent] = []
        self._received: set[ExpectationEventId] = set()
        self.calls = 0

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        self.calls += 1
        if event_id in self._received:
            return
        self._received.add(event_id)
        self.materials.append(event)


class _FailingReceiver(ExpectationEventReceiver):
    """最初の ``failures`` 回だけ例外を投げる受け取る側。"""

    def __init__(self, failures: int) -> None:
        self._remaining = failures
        self.received: list[ExpectationEventId] = []

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("belief store is busy")
        self.received.append(event_id)


def _settle_and_save(repository: InMemoryExpectationRepository) -> ExpectationSettled:
    expectation = Expectation(
        expectation_id=ExpectationId("exp-1"),
        holder=RIO,
        content="カイが焚き火を起こす",
        origin=ExpectationOrigin.PROMISE_OR_OUTLOOK,
        likelihood=Likelihood.PROBABLY,
        formed_at_turn=1,
        expires_at_turn=10,
    )
    expectation.record(Check(turn=2, verdict=CheckVerdict.HIT))
    event = expectation.record(Check(turn=3, verdict=CheckVerdict.HIT))
    assert isinstance(event, ExpectationSettled)
    repository.save(expectation, [event])
    return event


def _dispatcher(
    repository: InMemoryExpectationRepository,
    receivers: tuple[ExpectationEventReceiver, ...],
    recorder: RecordingTraceRecorder,
    *,
    max_attempts: int = 3,
) -> ExpectationEventDispatcher:
    return ExpectationEventDispatcher(
        repository,
        receivers=receivers,
        max_attempts=max_attempts,
        trace_recorder_provider=lambda: recorder,
    )


def _deliveries(recorder: RecordingTraceRecorder) -> list[dict[str, Any]]:
    return recorder.payloads(TraceEventKind.EXPECTATION_EVENT_DELIVERY)


class TestDeliverPending:
    """未配信の出来事を全員に配れたら印を付け、配れなければ残して次の呼び出しで配り直す挙動を保証する。"""

    def test_delivered_event_is_marked_and_traced(self) -> None:
        """全員が受け取れた出来事は配信済みになり、配った回数 1 と受け取る側の数を trace に残す。"""
        repository = InMemoryExpectationRepository()
        event = _settle_and_save(repository)
        receiver = _BeliefMaterialReceiver()
        recorder = RecordingTraceRecorder()

        _dispatcher(repository, (receiver,), recorder).deliver_pending(RIO)

        assert receiver.materials == [event]
        assert repository.list_undelivered_by_being(RIO) == []
        assert _deliveries(recorder) == [
            {
                "being_id": "being-rio",
                "event_id": "exp-1@3",
                "event_type": "ExpectationSettled",
                "outcome": "delivered",
                "attempts": 1,
                "receiver_count": 1,
                "receivers": ["_BeliefMaterialReceiver"],
            }
        ]

    def test_receiver_failure_keeps_event_and_next_call_redelivers(self) -> None:
        """受け取る側が例外を投げた出来事は未配信のまま理由とともに trace に残り、次の呼び出しで配り直され、配った回数 2 で配信済みになる。"""
        repository = InMemoryExpectationRepository()
        _settle_and_save(repository)
        receiver = _FailingReceiver(failures=1)
        recorder = RecordingTraceRecorder()
        dispatcher = _dispatcher(repository, (receiver,), recorder)

        dispatcher.deliver_pending(RIO)
        undelivered_after_failure = [
            u.event_id.value for u in repository.list_undelivered_by_being(RIO)
        ]
        dispatcher.deliver_pending(RIO)

        assert undelivered_after_failure == ["exp-1@3"]
        assert receiver.received == [ExpectationEventId("exp-1@3")]
        assert repository.list_undelivered_by_being(RIO) == []
        failed, delivered = _deliveries(recorder)
        assert failed["outcome"] == "failed"
        assert failed["attempts"] == 1
        assert failed["reason"] == "RuntimeError: belief store is busy"
        assert (delivered["outcome"], delivered["attempts"]) == ("delivered", 2)

    def test_redelivery_after_partial_failure_adds_material_only_once(self) -> None:
        """2 つ目の受け取る側が失敗して配り直すと、1 つ目にも同じ ID の出来事がもう一度届く。ID で重複を見分ける受け取る側なら、信念への材料は 1 回分だけ積まれる。本番の受け取る側の契約の試験は #1442 で足す。"""
        repository = InMemoryExpectationRepository()
        event = _settle_and_save(repository)
        belief = _BeliefMaterialReceiver()
        recorder = RecordingTraceRecorder()
        dispatcher = _dispatcher(
            repository, (belief, _FailingReceiver(failures=1)), recorder
        )

        dispatcher.deliver_pending(RIO)
        dispatcher.deliver_pending(RIO)

        assert belief.calls == 2
        assert belief.materials == [event]

    def test_restored_undelivered_event_is_delivered_by_new_dispatcher(self) -> None:
        """snapshot から戻した未配信の出来事は、再開した run の配り手が最初の呼び出しで配る。"""
        saved = InMemoryExpectationRepository()
        event = _settle_and_save(saved)
        resumed = InMemoryExpectationRepository()
        resumed.replace_all_by_being(
            RIO,
            expectations=saved.list_all_by_being(RIO),
            undelivered_events=saved.list_undelivered_by_being(RIO),
            turn=3,
        )
        receiver = _BeliefMaterialReceiver()

        _dispatcher(resumed, (receiver,), RecordingTraceRecorder()).deliver_pending(RIO)

        assert receiver.materials == [event]
        assert resumed.list_undelivered_by_being(RIO) == []

    def test_without_receivers_event_is_marked_delivered_as_no_receivers(self) -> None:
        """受け取る側が 1 つも無いとき、出来事は配信済みになり、誰かが受け取ったとは読めない no_receivers と受け取る側の数 0 を trace に残す。"""
        repository = InMemoryExpectationRepository()
        _settle_and_save(repository)
        recorder = RecordingTraceRecorder()

        _dispatcher(repository, (), recorder).deliver_pending(RIO)

        assert repository.list_undelivered_by_being(RIO) == []
        assert _deliveries(recorder)[0]["receiver_count"] == 0
        assert _deliveries(recorder)[0]["outcome"] == "no_receivers"


class TestAttemptLimit:
    """配り直しの回数の上限を超えた出来事を、捨てずに配り直しから外し、一覧と trace で見えるようにする挙動を保証する。"""

    def test_gives_up_after_max_attempts_and_lists_event(self) -> None:
        """上限回数まで失敗した出来事は、理由とともに諦めた記録を trace に残し、未配信のまま一覧に載り、以後の呼び出しでは配らない。"""
        repository = InMemoryExpectationRepository()
        _settle_and_save(repository)
        receiver = _FailingReceiver(failures=10)
        recorder = RecordingTraceRecorder()
        dispatcher = _dispatcher(repository, (receiver,), recorder, max_attempts=2)

        for _ in range(4):
            dispatcher.deliver_pending(RIO)

        outcomes = [(p["outcome"], p["attempts"]) for p in _deliveries(recorder)]
        assert outcomes == [("failed", 1), ("failed", 2), ("gave_up", 2)]
        assert _deliveries(recorder)[-1]["reason"] == "RuntimeError: belief store is busy"
        assert [u.event_id.value for u in dispatcher.undeliverable(RIO)] == ["exp-1@3"]
        assert len(repository.list_undelivered_by_being(RIO)) == 1

    def test_non_positive_max_attempts_raises(self) -> None:
        """配り直しの上限に 0 以下を渡すと ValueError を投げる。"""
        with pytest.raises(ValueError):
            _dispatcher(
                InMemoryExpectationRepository(), (), RecordingTraceRecorder(), max_attempts=0
            )
