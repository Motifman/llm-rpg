"""型付き相登録をCommandScopeの同期処理とcommit後handoffへ適合させる。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional, Sequence, Type

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.common.event_delivery import (
    AfterCommitEventHandler,
    EventDeliveryFailureObserver,
    EventDeliveryPhase,
    InTransactionEventHandler,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent


_PRE_COMMIT_PHASES = frozenset(
    {
        EventDeliveryPhase.CRITICAL_SYNC_SIDE_EFFECT,
        EventDeliveryPhase.BEST_EFFORT_SYNC_SIDE_EFFECT,
        EventDeliveryPhase.SYNC_OBSERVATION,
    }
)
_BEST_EFFORT_PHASES = frozenset(
    {
        EventDeliveryPhase.BEST_EFFORT_SYNC_SIDE_EFFECT,
        EventDeliveryPhase.SYNC_OBSERVATION,
    }
)
_POST_COMMIT_PHASES = frozenset(
    {
        EventDeliveryPhase.OBSERVE_AFTER_COMMIT,
        EventDeliveryPhase.ASYNC_POST_COMMIT,
    }
)


@dataclass(frozen=True)
class _Registration:
    event_type: Type[DomainEvent]
    phase: EventDeliveryPhase
    handler: object


class PhasedCommandEventDispatcher:
    """登録順を保ちながらcommit前とcommit後のhandlerを分離して実行する。"""

    def __init__(
        self,
        *,
        failure_observer: Optional[EventDeliveryFailureObserver] = None,
    ) -> None:
        self._registrations: list[_Registration] = []
        self._failure_observer = failure_observer
        self._logger = logging.getLogger(self.__class__.__name__)

    def register_critical_sync(
        self,
        event_type: Type[DomainEvent],
        handler: InTransactionEventHandler,
    ) -> None:
        """失敗をcommandへ伝播させる同期handlerを登録する。"""
        self._register(
            event_type,
            EventDeliveryPhase.CRITICAL_SYNC_SIDE_EFFECT,
            handler,
        )

    def register_best_effort_sync(
        self,
        event_type: Type[DomainEvent],
        handler: InTransactionEventHandler,
    ) -> None:
        """失敗を観測してcommandを継続する補助handlerを登録する。"""
        self._register(
            event_type,
            EventDeliveryPhase.BEST_EFFORT_SYNC_SIDE_EFFECT,
            handler,
        )

    def register_sync_observation(
        self,
        event_type: Type[DomainEvent],
        handler: InTransactionEventHandler,
    ) -> None:
        """commit前の順序や状態を読む観測handlerを登録する。"""
        self._register(event_type, EventDeliveryPhase.SYNC_OBSERVATION, handler)

    def register_observe_after_commit(
        self,
        event_type: Type[DomainEvent],
        handler: AfterCommitEventHandler,
    ) -> None:
        """確定状態に追随する通常観測handlerを登録する。"""
        self._register(event_type, EventDeliveryPhase.OBSERVE_AFTER_COMMIT, handler)

    def register_async_post_commit(
        self,
        event_type: Type[DomainEvent],
        handler: AfterCommitEventHandler,
    ) -> None:
        """outboxへの移行対象となるcommit後配送handlerを登録する。"""
        self._register(event_type, EventDeliveryPhase.ASYNC_POST_COMMIT, handler)

    def dispatch(self, event: DomainEvent, context: CommandContext) -> None:
        """commit前3相だけを登録順に実行する。"""
        for registration in self._matching_registrations(event, _PRE_COMMIT_PHASES):
            handler = registration.handler
            try:
                if not callable(handler):
                    raise TypeError("commit前event handlerは呼出し可能である必要があります")
                handler(event, context)
            except Exception as error:
                if registration.phase not in _BEST_EFFORT_PHASES:
                    raise
                self._observe_best_effort_failure(registration, event, error)

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        """commit後2相だけをイベント順・登録順で実行する。"""
        for event in events:
            for registration in self._matching_registrations(
                event,
                _POST_COMMIT_PHASES,
            ):
                handler = registration.handler
                if not callable(handler):
                    raise TypeError("commit後event handlerは呼出し可能である必要があります")
                handler(event)

    def _register(
        self,
        event_type: Type[DomainEvent],
        phase: EventDeliveryPhase,
        handler: object,
    ) -> None:
        if not isinstance(event_type, type):
            raise TypeError("event_typeは型である必要があります")
        if not callable(handler):
            raise TypeError("event handlerは呼出し可能である必要があります")
        self._registrations.append(_Registration(event_type, phase, handler))

    def _matching_registrations(
        self,
        event: DomainEvent,
        phases: frozenset[EventDeliveryPhase],
    ) -> list[_Registration]:
        return [
            registration
            for registration in self._registrations
            if registration.phase in phases
            and isinstance(event, registration.event_type)
        ]

    def _observe_best_effort_failure(
        self,
        registration: _Registration,
        event: DomainEvent,
        error: Exception,
    ) -> None:
        self._logger.warning(
            "Best-effort event handler failed: phase=%s event_type=%s handler=%r",
            registration.phase.value,
            type(event).__name__,
            registration.handler,
            exc_info=error,
        )
        if self._failure_observer is None:
            return
        try:
            self._failure_observer(
                registration.phase,
                event,
                registration.handler,
                error,
            )
        except Exception:
            self._logger.exception(
                "Best-effort event failure observer failed: phase=%s event_type=%s",
                registration.phase.value,
                type(event).__name__,
            )


__all__ = ["PhasedCommandEventDispatcher"]
