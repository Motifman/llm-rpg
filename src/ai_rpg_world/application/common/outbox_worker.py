"""commit済みoutboxイベントを順序付きで再配送するユースケース。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.domain.common.domain_event import DomainEvent


@dataclass(frozen=True)
class StoredOutboxMessage:
    """outboxから取得した未配送メッセージ。"""

    event_id: str
    event_type: str
    payload: bytes
    payload_schema_version: int


@dataclass(frozen=True)
class OutboxRunResult:
    """1回のworker実行で確定した件数。"""

    delivered_count: int
    rejected_count: int


class PermanentOutboxMessageException(ApplicationException):
    """再試行しても復元できないoutboxメッセージを表す。"""


class OutboxDeliveryException(ApplicationException):
    """handler配送に失敗し、メッセージをpendingに残したことを表す。"""

    def __init__(
        self,
        *,
        event_id: str,
        delivered_count: int,
        delivery_error: Exception,
        recording_error: Exception | None = None,
    ) -> None:
        self.event_id = event_id
        self.delivered_count = delivered_count
        self.delivery_error = delivery_error
        self.recording_error = recording_error
        super().__init__(
            "outboxイベントの再配送に失敗しました: "
            f"event_id={event_id}",
            cause=delivery_error,
            event_id=event_id,
            delivered_count=delivered_count,
            delivery_error=delivery_error,
            recording_error=recording_error,
        )


class OutboxAcknowledgementException(ApplicationException):
    """handler配送後のdelivered記録失敗を表す。"""

    def __init__(
        self,
        *,
        event_id: str,
        delivered_count: int,
        acknowledgement_error: Exception,
    ) -> None:
        self.event_id = event_id
        self.delivered_count = delivered_count
        self.acknowledgement_error = acknowledgement_error
        super().__init__(
            "outboxイベントは配送済みですがdelivered記録に失敗しました。"
            "次回実行で重複配送される可能性があります: "
            f"event_id={event_id}",
            cause=acknowledgement_error,
            event_id=event_id,
            delivered_count=delivered_count,
            acknowledgement_error=acknowledgement_error,
        )


class OutboxRejectionException(ApplicationException):
    """復元不能なメッセージの隔離記録失敗を表す。"""

    def __init__(
        self,
        *,
        event_id: str,
        rejection_error: Exception,
        message_error: Exception,
    ) -> None:
        self.event_id = event_id
        self.rejection_error = rejection_error
        self.message_error = message_error
        super().__init__(
            "復元不能なoutboxイベントをrejectedへ隔離できませんでした: "
            f"event_id={event_id}",
            cause=rejection_error,
            event_id=event_id,
            rejection_error=rejection_error,
            message_error=message_error,
        )


class OutboxDeliveryStorePort(Protocol):
    """workerが必要とするoutbox状態変更の最小契約。"""

    def fetch_pending(self, *, limit: int) -> Sequence[StoredOutboxMessage]: ...

    def mark_delivered(self, event_id: str) -> None: ...

    def record_retryable_failure(self, event_id: str, error: Exception) -> None: ...

    def mark_rejected(self, event_id: str, error: Exception) -> None: ...


class OutboxEventDeserializerPort(Protocol):
    """保存メッセージを型付きドメインイベントへ戻す契約。"""

    def deserialize(self, message: StoredOutboxMessage) -> DomainEvent: ...


class DurableEventHandoffPort(Protocol):
    """再送必須handlerだけへイベントを渡す契約。"""

    def handoff_durable(self, events: Sequence[DomainEvent]) -> None: ...


class OutboxWorker:
    """pendingイベントを1件ずつ配送し、成功した行だけ確定する。"""

    def __init__(
        self,
        store: OutboxDeliveryStorePort,
        deserializer: OutboxEventDeserializerPort,
        handoff: DurableEventHandoffPort,
    ) -> None:
        self._store = store
        self._deserializer = deserializer
        self._handoff = handoff

    def run_once(self, *, limit: int = 100) -> OutboxRunResult:
        """最大limit件を順序付きで配送し、一時失敗で停止する。"""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limitは1以上の整数である必要があります")
        delivered_count = 0
        rejected_count = 0
        for message in self._store.fetch_pending(limit=limit):
            try:
                event = self._deserializer.deserialize(message)
            except PermanentOutboxMessageException as error:
                try:
                    self._store.mark_rejected(message.event_id, error)
                except Exception as rejection_error:
                    raise OutboxRejectionException(
                        event_id=message.event_id,
                        rejection_error=rejection_error,
                        message_error=error,
                    ) from rejection_error
                rejected_count += 1
                continue
            try:
                self._handoff.handoff_durable((event,))
            except Exception as error:
                recording_error: Exception | None = None
                try:
                    self._store.record_retryable_failure(message.event_id, error)
                except Exception as caught_recording_error:
                    recording_error = caught_recording_error
                raise OutboxDeliveryException(
                    event_id=message.event_id,
                    delivered_count=delivered_count,
                    delivery_error=error,
                    recording_error=recording_error,
                ) from (recording_error or error)
            try:
                self._store.mark_delivered(message.event_id)
            except Exception as acknowledgement_error:
                raise OutboxAcknowledgementException(
                    event_id=message.event_id,
                    delivered_count=delivered_count,
                    acknowledgement_error=acknowledgement_error,
                ) from acknowledgement_error
            delivered_count += 1
        return OutboxRunResult(
            delivered_count=delivered_count,
            rejected_count=rejected_count,
        )


__all__ = [
    "DurableEventHandoffPort",
    "OutboxAcknowledgementException",
    "OutboxDeliveryException",
    "OutboxDeliveryStorePort",
    "OutboxEventDeserializerPort",
    "OutboxRunResult",
    "OutboxRejectionException",
    "OutboxWorker",
    "PermanentOutboxMessageException",
    "StoredOutboxMessage",
]
