"""commit済みoutboxイベントを順序付きで再配送するユースケース。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Protocol, Sequence

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.domain.common.domain_event import DomainEvent

_MAX_RETRY_DELAY_SECONDS = 31_536_000.0


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
    dead_lettered_count: int = 0


@dataclass(frozen=True)
class OutboxRetryPolicy:
    """一時失敗を再試行する回数と指数的な待機時間。"""

    max_attempts: int = 12
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attemptsは1以上の整数である必要があります")
        for name, value in (
            ("initial_delay_seconds", self.initial_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                or value > _MAX_RETRY_DELAY_SECONDS
            ):
                raise ValueError(
                    f"{name}は0より大きく365日以下である必要があります"
                )
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError(
                "max_delay_secondsはinitial_delay_seconds以上である必要があります"
            )

    def delay_after(self, attempt_count: int) -> timedelta:
        """今回までの失敗回数から、次回までの待機時間を返す。"""
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 1
        ):
            raise ValueError("attempt_countは1以上の整数である必要があります")
        delay = float(self.initial_delay_seconds)
        for _ in range(attempt_count - 1):
            if delay >= self.max_delay_seconds / 2:
                delay = float(self.max_delay_seconds)
                break
            delay *= 2
        return timedelta(seconds=min(delay, self.max_delay_seconds))


@dataclass(frozen=True)
class OutboxFailureDisposition:
    """一時失敗を記録した後の永続状態。"""

    attempt_count: int
    next_attempt_at: datetime | None
    dead_lettered: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt_count, bool)
            or not isinstance(self.attempt_count, int)
            or self.attempt_count < 1
        ):
            raise ValueError("attempt_countは1以上の整数である必要があります")
        if self.dead_lettered != (self.next_attempt_at is None):
            raise ValueError(
                "dead letterと次回試行時刻を同時に設定することはできません"
            )
        if self.next_attempt_at is not None and (
            self.next_attempt_at.tzinfo is None
            or self.next_attempt_at.utcoffset() is None
        ):
            raise ValueError("next_attempt_atにはタイムゾーン付き日時が必要です")


class PermanentOutboxMessageException(ApplicationException):
    """再試行しても復元できないoutboxメッセージを表す。"""


class OutboxNoDurableHandlerException(ApplicationException):
    """復元イベントを処理する再送必須handlerが登録されていないことを表す。"""

    def __init__(self, *, event_id: str, event_type: str) -> None:
        self.event_id = event_id
        self.event_type = event_type
        super().__init__(
            "outboxイベントを処理するDURABLE_RETRY handlerがありません: "
            f"event_id={event_id}, event_type={event_type}",
            event_id=event_id,
            event_type=event_type,
        )


class OutboxDeliveryException(ApplicationException):
    """handler配送に失敗し、メッセージをpendingに残したことを表す。"""

    def __init__(
        self,
        *,
        event_id: str,
        delivered_count: int,
        delivery_error: Exception,
        recording_error: Exception | None = None,
        attempt_count: int | None = None,
        next_attempt_at: datetime | None = None,
        dead_lettered_count: int = 0,
    ) -> None:
        self.event_id = event_id
        self.delivered_count = delivered_count
        self.delivery_error = delivery_error
        self.recording_error = recording_error
        self.attempt_count = attempt_count
        self.next_attempt_at = next_attempt_at
        self.dead_lettered_count = dead_lettered_count
        retry_details = ""
        if attempt_count is not None and next_attempt_at is not None:
            retry_details = (
                f", attempt_count={attempt_count}, "
                f"next_attempt_at={next_attempt_at.isoformat()}"
            )
        super().__init__(
            "outboxイベントの再配送に失敗しました: "
            f"event_id={event_id}{retry_details}",
            cause=delivery_error,
            event_id=event_id,
            delivered_count=delivered_count,
            delivery_error=delivery_error,
            recording_error=recording_error,
            attempt_count=attempt_count,
            next_attempt_at=next_attempt_at,
            dead_lettered_count=dead_lettered_count,
        )


class OutboxAcknowledgementException(ApplicationException):
    """handler配送後のdelivered記録失敗を表す。"""

    def __init__(
        self,
        *,
        event_id: str,
        delivered_count: int,
        acknowledgement_error: Exception,
        dead_lettered_count: int = 0,
    ) -> None:
        self.event_id = event_id
        self.delivered_count = delivered_count
        self.acknowledgement_error = acknowledgement_error
        self.dead_lettered_count = dead_lettered_count
        super().__init__(
            "outboxイベントは配送済みですがdelivered記録に失敗しました。"
            "次回実行で重複配送される可能性があります: "
            f"event_id={event_id}",
            cause=acknowledgement_error,
            event_id=event_id,
            delivered_count=delivered_count,
            acknowledgement_error=acknowledgement_error,
            dead_lettered_count=dead_lettered_count,
        )


class OutboxRejectionException(ApplicationException):
    """復元不能なメッセージの隔離記録失敗を表す。"""

    def __init__(
        self,
        *,
        event_id: str,
        rejection_error: Exception,
        message_error: Exception,
        dead_lettered_count: int = 0,
    ) -> None:
        self.event_id = event_id
        self.rejection_error = rejection_error
        self.message_error = message_error
        self.dead_lettered_count = dead_lettered_count
        super().__init__(
            "復元不能なoutboxイベントをrejectedへ隔離できませんでした: "
            f"event_id={event_id}",
            cause=rejection_error,
            event_id=event_id,
            rejection_error=rejection_error,
            message_error=message_error,
            dead_lettered_count=dead_lettered_count,
        )


class OutboxDeliveryStorePort(Protocol):
    """workerが必要とするoutbox状態変更の最小契約。"""

    def fetch_pending(self, *, limit: int) -> Sequence[StoredOutboxMessage]: ...

    def mark_delivered(self, event_id: str) -> None: ...

    def record_retryable_failure(
        self, event_id: str, error: Exception
    ) -> OutboxFailureDisposition: ...

    def mark_rejected(self, event_id: str, error: Exception) -> None: ...


class OutboxEventDeserializerPort(Protocol):
    """保存メッセージを型付きドメインイベントへ戻す契約。"""

    def deserialize(self, message: StoredOutboxMessage) -> DomainEvent: ...


class DurableEventHandoffPort(Protocol):
    """再送必須handlerだけへイベントを渡す契約。"""

    def handoff_durable(self, events: Sequence[DomainEvent]) -> int:
        """実行した再送必須handlerの総数を返す。"""
        ...


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
        dead_lettered_count = 0
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
                        dead_lettered_count=dead_lettered_count,
                    ) from rejection_error
                rejected_count += 1
                continue
            try:
                handled_count = self._handoff.handoff_durable((event,))
                if handled_count < 1:
                    raise OutboxNoDurableHandlerException(
                        event_id=message.event_id,
                        event_type=message.event_type,
                    )
            except Exception as error:
                recording_error: Exception | None = None
                disposition: OutboxFailureDisposition | None = None
                try:
                    disposition = self._store.record_retryable_failure(
                        message.event_id,
                        error,
                    )
                except Exception as caught_recording_error:
                    recording_error = caught_recording_error
                if disposition is not None and disposition.dead_lettered:
                    dead_lettered_count += 1
                    continue
                raise OutboxDeliveryException(
                    event_id=message.event_id,
                    delivered_count=delivered_count,
                    delivery_error=error,
                    recording_error=recording_error,
                    attempt_count=(
                        None if disposition is None else disposition.attempt_count
                    ),
                    next_attempt_at=(
                        None if disposition is None else disposition.next_attempt_at
                    ),
                    dead_lettered_count=dead_lettered_count,
                ) from (recording_error or error)
            try:
                self._store.mark_delivered(message.event_id)
            except Exception as acknowledgement_error:
                raise OutboxAcknowledgementException(
                    event_id=message.event_id,
                    delivered_count=delivered_count,
                    acknowledgement_error=acknowledgement_error,
                    dead_lettered_count=dead_lettered_count,
                ) from acknowledgement_error
            delivered_count += 1
        return OutboxRunResult(
            delivered_count=delivered_count,
            rejected_count=rejected_count,
            dead_lettered_count=dead_lettered_count,
        )


__all__ = [
    "DurableEventHandoffPort",
    "OutboxAcknowledgementException",
    "OutboxDeliveryException",
    "OutboxDeliveryStorePort",
    "OutboxEventDeserializerPort",
    "OutboxFailureDisposition",
    "OutboxNoDurableHandlerException",
    "OutboxRunResult",
    "OutboxRejectionException",
    "OutboxRetryPolicy",
    "OutboxWorker",
    "PermanentOutboxMessageException",
    "StoredOutboxMessage",
]
