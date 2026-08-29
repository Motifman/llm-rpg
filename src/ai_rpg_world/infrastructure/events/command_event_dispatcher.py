"""二相のイベント登録をCommandScopeの同期処理とcommit後handoffへ適合させる。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional, Sequence, Type

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.common.event_delivery import (
    AfterCommitFailureObserver,
    AfterCommitHandler,
    DeliveryChannel,
    DeliveryGuarantee,
    RequiredBeforeCommitHandler,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent


@dataclass(frozen=True)
class _BeforeCommitRegistration:
    event_type: Type[DomainEvent]
    handler: RequiredBeforeCommitHandler


@dataclass(frozen=True)
class _AfterCommitRegistration:
    event_type: Type[DomainEvent]
    handler: AfterCommitHandler
    channel: DeliveryChannel
    guarantee: DeliveryGuarantee


class CommandEventDispatcher:
    """必須処理をcommit前、その他の処理をcommit後に限定して実行する。"""

    def __init__(
        self,
        *,
        failure_observer: Optional[AfterCommitFailureObserver] = None,
    ) -> None:
        self._before_commit: list[_BeforeCommitRegistration] = []
        self._after_commit: list[_AfterCommitRegistration] = []
        self._failure_observer = failure_observer
        self._logger = logging.getLogger(self.__class__.__name__)

    def register_required_before_commit(
        self,
        event_type: Type[DomainEvent],
        handler: RequiredBeforeCommitHandler,
    ) -> None:
        """失敗時にcommand全体を戻す必須handlerを登録する。"""
        self._validate_registration(event_type, handler)
        self._before_commit.append(_BeforeCommitRegistration(event_type, handler))

    def register_after_commit(
        self,
        event_type: Type[DomainEvent],
        handler: AfterCommitHandler,
        *,
        channel: DeliveryChannel,
        guarantee: DeliveryGuarantee,
    ) -> None:
        """確定状態へ追随するhandlerを配送先・保証付きで登録する。"""
        self._validate_registration(event_type, handler)
        if not isinstance(channel, DeliveryChannel):
            raise TypeError("channelはDeliveryChannelである必要があります")
        if not isinstance(guarantee, DeliveryGuarantee):
            raise TypeError("guaranteeはDeliveryGuaranteeである必要があります")
        self._after_commit.append(
            _AfterCommitRegistration(event_type, handler, channel, guarantee)
        )

    def dispatch(self, event: DomainEvent, context: CommandContext) -> None:
        """commit前必須handlerだけを登録順に実行し、例外を伝播する。"""
        for registration in self._before_commit:
            if isinstance(event, registration.event_type):
                registration.handler(event, context)

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        """commit後handlerをイベント順・登録順で実行する。"""
        for event in events:
            for registration in self._after_commit:
                if not isinstance(event, registration.event_type):
                    continue
                try:
                    registration.handler(event)
                except Exception as error:
                    if registration.guarantee is DeliveryGuarantee.DURABLE_RETRY:
                        raise
                    self._observe_best_effort_failure(registration, event, error)

    def handoff_durable(self, events: Sequence[DomainEvent]) -> int:
        """outbox再配送時にDURABLE_RETRY handlerだけを実行し件数を返す。"""
        handled_count = 0
        for event in events:
            for registration in self._after_commit:
                if (
                    isinstance(event, registration.event_type)
                    and registration.guarantee is DeliveryGuarantee.DURABLE_RETRY
                ):
                    registration.handler(event)
                    handled_count += 1
        return handled_count

    def requires_durable_retry(self, event: DomainEvent) -> bool:
        """少なくとも1つの再送必須handlerが対象ならTrueを返す。"""
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

    def _observe_best_effort_failure(
        self,
        registration: _AfterCommitRegistration,
        event: DomainEvent,
        error: Exception,
    ) -> None:
        self._logger.warning(
            "Best-effort after-commit handler failed: channel=%s "
            "event_type=%s handler=%r",
            registration.channel.value,
            type(event).__name__,
            registration.handler,
            exc_info=error,
        )
        if self._failure_observer is None:
            return
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


__all__ = ["CommandEventDispatcher"]
