"""OutboxWorkerの順序付き配送と失敗分類を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.common.outbox_worker import (
    OutboxAcknowledgementException,
    OutboxDeliveryException,
    OutboxRejectionException,
    OutboxWorker,
    PermanentOutboxMessageException,
    StoredOutboxMessage,
)
from ai_rpg_world.domain.trade.event.trade_event import TradeCancelledEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId


class _Store:
    def __init__(
        self,
        messages=(),
        *,
        fail_delivered: bool = False,
        fail_retryable: bool = False,
        fail_rejected: bool = False,
    ) -> None:
        self.messages = tuple(messages)
        self.fail_delivered = fail_delivered
        self.fail_retryable = fail_retryable
        self.fail_rejected = fail_rejected
        self.delivered: list[str] = []
        self.retryable: list[str] = []
        self.rejected: list[str] = []
        self.requested_limits: list[int] = []

    def fetch_pending(self, *, limit: int):
        self.requested_limits.append(limit)
        return self.messages[:limit]

    def mark_delivered(self, event_id: str) -> None:
        if self.fail_delivered:
            raise RuntimeError("ack failed")
        self.delivered.append(event_id)

    def record_retryable_failure(self, event_id: str, error: Exception) -> None:
        if self.fail_retryable:
            raise RuntimeError("failure record failed")
        self.retryable.append(event_id)

    def mark_rejected(self, event_id: str, error: Exception) -> None:
        if self.fail_rejected:
            raise RuntimeError("rejection record failed")
        self.rejected.append(event_id)


class _Deserializer:
    def __init__(self, *, rejected_ids=()) -> None:
        self.rejected_ids = frozenset(rejected_ids)

    def deserialize(self, message: StoredOutboxMessage):
        if message.event_id in self.rejected_ids:
            raise PermanentOutboxMessageException("broken payload")
        return TradeCancelledEvent(
            event_id=int(message.event_id),
            occurred_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )


class _Handoff:
    def __init__(self, *, failing_event_id: int | None = None) -> None:
        self.failing_event_id = failing_event_id
        self.event_ids: list[int] = []

    def handoff_durable(self, events) -> None:
        event = events[0]
        self.event_ids.append(event.event_id)
        if event.event_id == self.failing_event_id:
            raise RuntimeError("temporary failure")


def _message(event_id: int) -> StoredOutboxMessage:
    return StoredOutboxMessage(
        event_id=str(event_id),
        event_type=f"{TradeCancelledEvent.__module__}:{TradeCancelledEvent.__qualname__}",
        payload=b"{}",
        payload_schema_version=1,
    )


def test_empty_outbox_returns_zero_without_handoff() -> None:
    """pending行がないときは配送や状態更新を行わず0件を返す。"""
    store = _Store()
    handoff = _Handoff()

    result = OutboxWorker(store, _Deserializer(), handoff).run_once(limit=5)

    assert result.delivered_count == 0
    assert result.rejected_count == 0
    assert store.requested_limits == [5]
    assert handoff.event_ids == []


def test_successful_messages_are_acknowledged_one_by_one_in_order() -> None:
    """取得順に1件ずつ配送し、handler成功後だけdeliveredへ更新する。"""
    store = _Store((_message(1), _message(2)))
    handoff = _Handoff()

    result = OutboxWorker(store, _Deserializer(), handoff).run_once()

    assert result.delivered_count == 2
    assert handoff.event_ids == [1, 2]
    assert store.delivered == ["1", "2"]


def test_retryable_failure_keeps_current_message_and_stops_later_delivery() -> None:
    """handlerの一時失敗は対象をpendingに残し、後続イベントの順序追い越しを防ぐ。"""
    store = _Store((_message(1), _message(2), _message(3)))
    handoff = _Handoff(failing_event_id=2)

    with pytest.raises(OutboxDeliveryException) as caught:
        OutboxWorker(store, _Deserializer(), handoff).run_once()

    assert caught.value.event_id == "2"
    assert caught.value.delivered_count == 1
    assert handoff.event_ids == [1, 2]
    assert store.delivered == ["1"]
    assert store.retryable == ["2"]


def test_retryable_failure_preserves_delivery_and_recording_errors() -> None:
    """一時失敗の記録にも失敗したときは配送・記録の両エラーを保持する。"""
    store = _Store((_message(1),), fail_retryable=True)
    handoff = _Handoff(failing_event_id=1)

    with pytest.raises(OutboxDeliveryException) as caught:
        OutboxWorker(store, _Deserializer(), handoff).run_once()

    assert str(caught.value.delivery_error) == "temporary failure"
    assert str(caught.value.recording_error) == "failure record failed"
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_acknowledgement_failure_reports_possible_duplicate_delivery() -> None:
    """配送後のdelivered更新失敗は重複配送の可能性がある専用例外にする。"""
    store = _Store((_message(1),), fail_delivered=True)
    handoff = _Handoff()

    with pytest.raises(OutboxAcknowledgementException) as caught:
        OutboxWorker(store, _Deserializer(), handoff).run_once()

    assert caught.value.event_id == "1"
    assert caught.value.delivered_count == 0
    assert str(caught.value.acknowledgement_error) == "ack failed"
    assert handoff.event_ids == [1]


def test_rejection_record_failure_stops_before_later_delivery() -> None:
    """復元不能行の隔離に失敗したときは後続を追い越して配送しない。"""
    store = _Store((_message(1), _message(2)), fail_rejected=True)
    handoff = _Handoff()

    with pytest.raises(OutboxRejectionException) as caught:
        OutboxWorker(
            store,
            _Deserializer(rejected_ids=("1",)),
            handoff,
        ).run_once()

    assert caught.value.event_id == "1"
    assert str(caught.value.rejection_error) == "rejection record failed"
    assert handoff.event_ids == []


def test_permanent_payload_failure_is_rejected_and_next_message_continues() -> None:
    """復元不能な行は通常再試行から隔離し、復元可能な後続行は配送する。"""
    store = _Store((_message(1), _message(2)))
    handoff = _Handoff()

    result = OutboxWorker(
        store,
        _Deserializer(rejected_ids=("1",)),
        handoff,
    ).run_once()

    assert result.rejected_count == 1
    assert result.delivered_count == 1
    assert store.rejected == ["1"]
    assert store.delivered == ["2"]
    assert handoff.event_ids == [2]


@pytest.mark.parametrize("limit", (True, 0, -1, 1.5))
def test_invalid_limit_is_rejected_before_store_access(limit: object) -> None:
    """limitが正の整数でないときはoutboxを読む前に拒否する。"""
    store = _Store()

    with pytest.raises(ValueError, match="limit"):
        OutboxWorker(store, _Deserializer(), _Handoff()).run_once(limit=limit)  # type: ignore[arg-type]

    assert store.requested_limits == []
