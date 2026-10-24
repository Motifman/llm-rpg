"""確定の前後で受け手を同期的に呼ぶ、文脈に依存しない配送器。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

from ai_rpg_world.eventing.delivery import (
    AfterCommitFailureObserver,
    AfterCommitHandler,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.eventing.domain_event import DomainEvent

_Event = TypeVar("_Event", bound=DomainEvent)
_Context = TypeVar("_Context")


@dataclass(frozen=True)
class _BeforeCommitRegistration(Generic[_Context]):
    event_type: type[DomainEvent]
    handler: Callable[[DomainEvent, _Context], None]


@dataclass(frozen=True)
class _AfterCommitRegistration:
    event_type: type[DomainEvent]
    handler: AfterCommitHandler
    channel: DeliveryChannel
    guarantee: DeliveryGuarantee


class EventDispatcher(Generic[_Context]):
    """確定前の必須処理と、確定後の配送を登録順に実行する。"""

    def __init__(
        self,
        *,
        failure_observer: AfterCommitFailureObserver,
    ) -> None:
        if not callable(failure_observer):
            raise TypeError("failure_observerは呼び出せる関数である必要があります")
        self._before_commit: list[_BeforeCommitRegistration[_Context]] = []
        self._after_commit: list[_AfterCommitRegistration] = []
        self._failure_observer = failure_observer
        self._logger = logging.getLogger(self.__class__.__name__)

    def register_required_before_commit(
        self,
        event_type: type[_Event],
        handler: Callable[[_Event, _Context], None],
    ) -> None:
        """失敗を呼び出し元に伝える、確定前の必須処理を登録する。"""
        self._validate_registration(event_type, handler)
        # 登録時に型引数で結んだイベントと受け手を、型の照合後に呼ぶ。
        self._before_commit.append(
            _BeforeCommitRegistration(
                event_type, cast("Callable[[DomainEvent, _Context], None]", handler)
            )
        )

    def register_after_commit(
        self,
        event_type: type[_Event],
        handler: Callable[[_Event], None],
        *,
        channel: DeliveryChannel,
        guarantee: DeliveryGuarantee,
    ) -> None:
        """確定後の受け手を配送先と保証付きで登録する。"""
        self._validate_registration(event_type, handler)
        if not isinstance(channel, DeliveryChannel):
            raise TypeError("channelはDeliveryChannelである必要があります")
        if not isinstance(guarantee, DeliveryGuarantee):
            raise TypeError("guaranteeはDeliveryGuaranteeである必要があります")
        self._after_commit.append(
            _AfterCommitRegistration(
                event_type, cast("AfterCommitHandler", handler), channel, guarantee
            )
        )

    def dispatch(self, event: DomainEvent, context: _Context) -> None:
        """確定前の必須処理だけを登録順に実行し、例外を伝える。"""
        for registration in self._before_commit:
            if isinstance(event, registration.event_type):
                registration.handler(event, context)

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        """全受け手をイベント順・登録順に呼び、最後に最初の再送必須の失敗を返す。"""
        self._handoff(events, durable_only=False)

    def handoff_durable(self, events: Sequence[DomainEvent]) -> int:
        """再送必須の受け手だけを呼び、全件成功なら実行した件数を返す。"""
        return self._handoff(events, durable_only=True)

    def _handoff(self, events: Sequence[DomainEvent], *, durable_only: bool) -> int:
        first_error: Exception | None = None
        handled_count = 0
        for event in events:
            for registration in self._after_commit:
                if not isinstance(event, registration.event_type):
                    continue
                if durable_only and registration.guarantee is not DeliveryGuarantee.DURABLE_RETRY:
                    continue
                try:
                    registration.handler(event)
                    handled_count += 1
                except Exception as error:
                    self._observe_failure(registration, event, error)
                    if registration.guarantee is DeliveryGuarantee.DURABLE_RETRY and first_error is None:
                        first_error = error
        if first_error is not None:
            raise first_error
        return handled_count

    def requires_durable_retry(self, event: DomainEvent) -> bool:
        """再送必須の受け手が一つでも対象なら True を返す。"""
        return any(
            isinstance(event, registration.event_type)
            and registration.guarantee is DeliveryGuarantee.DURABLE_RETRY
            for registration in self._after_commit
        )

    @staticmethod
    def _validate_registration(event_type: object, handler: object) -> None:
        if not isinstance(event_type, type):
            raise TypeError("event_typeは型である必要があります")
        if not callable(handler):
            raise TypeError("event handlerは呼出し可能である必要があります")

    def _observe_failure(
        self,
        registration: _AfterCommitRegistration,
        event: DomainEvent,
        error: Exception,
    ) -> None:
        self._logger.warning(
            "%s after-commit handler failed: channel=%s "
            "event_type=%s handler=%r",
            "Best-effort" if registration.guarantee is DeliveryGuarantee.BEST_EFFORT else "Durable-retry",
            registration.channel.value,
            type(event).__name__,
            registration.handler,
            exc_info=error,
        )
        try:
            self._failure_observer(
                registration.channel,
                registration.guarantee,
                event,
                registration.handler,
                error,
            )
        except Exception:
            self._logger.exception(
                "After-commit failure observer failed: channel=%s event_type=%s",
                registration.channel.value,
                type(event).__name__,
            )


__all__ = ["EventDispatcher"]
