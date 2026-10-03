"""予期の出来事を、保存のあとで受け取る側へ配る (アウトボックスの配り手)。

出来事は予期と同じ保存の単位で未配信として積まれている (design_decisions D1439)。
ここは積まれた出来事を配り、全員が受け取れたら配信済みの印を付けるだけで、
出来事を作らない。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
)
from ai_rpg_world.domain.memory.expectation.repository.expectation_repository import (
    ExpectationRepository,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
    UndeliveredExpectationEvent,
)

logger = logging.getLogger(__name__)


class ExpectationEventReceiver(ABC):
    """予期の出来事を受け取る側の契約。

    **同じ ``event_id`` を二度受け取っても、結果が変わらない作りにする。**
    配り手は、受け取る側の誰か 1 つでも例外を投げたら出来事を未配信のまま残し、
    次に全員へ配り直す。先に受け取れた側にも同じ出来事がもう一度届く。
    受け取り済みの ID は、受け取った結果と同じ保存の単位で記録する (#1479)。
    """

    @abstractmethod
    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        """受け取れなかったときは例外を投げる。配り手が理由を trace に残して配り直す。"""


class ExpectationEventDispatcher:
    """未配信の出来事を受け取る側へ配り、配れなかった出来事を次の呼び出しで配り直す。

    配ろうとした回数は run の中だけで数える。上限に届いた出来事は配り直しから
    外すが、未配信のまま保存先に残す。確定した予期の出来事は、配り終えるまで
    失わない (#1479)。再開した run では数え直し、もう一度配る。
    """

    def __init__(
        self,
        repository: ExpectationRepository,
        *,
        receivers: Sequence[ExpectationEventReceiver],
        max_attempts: int,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        if not isinstance(repository, ExpectationRepository):
            raise TypeError("repository must be ExpectationRepository")
        if not all(isinstance(r, ExpectationEventReceiver) for r in receivers):
            raise TypeError("receivers must be ExpectationEventReceiver")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise TypeError("max_attempts must be int")
        if max_attempts < 1:
            raise ValueError("max_attempts must be 1 or greater")
        self._repository = repository
        self._receivers = tuple(receivers)
        self._max_attempts = max_attempts
        self._trace_recorder_provider = trace_recorder_provider
        self._attempts: dict[ExpectationEventId, int] = {}
        self._given_up: dict[BeingId, list[UndeliveredExpectationEvent]] = {}

    def deliver_pending(
        self,
        being_id: BeingId,
        *,
        tick: int | None = None,
        player_id: int | None = None,
    ) -> None:
        """未配信の出来事を保存した順に配る。``tick`` と ``player_id`` は trace に載せるだけ。"""
        given_up = {entry.event_id for entry in self._given_up.get(being_id, [])}
        for entry in self._repository.list_undelivered_by_being(being_id):
            if entry.event_id in given_up:
                continue
            attempts = self._attempts.get(entry.event_id, 0) + 1
            self._attempts[entry.event_id] = attempts
            failure = self._deliver(entry)
            if failure is None:
                self._repository.mark_delivered(being_id, entry.event_id)
                del self._attempts[entry.event_id]
                # 受け取る側が無いあいだの印は、誰かが受け取ったとは読めない値で残す。
                outcome = "delivered" if self._receivers else "no_receivers"
                self._trace(being_id, entry, outcome, attempts, tick, player_id)
                continue
            self._trace(
                being_id, entry, "failed", attempts, tick, player_id, reason=failure
            )
            if attempts >= self._max_attempts:
                self._given_up.setdefault(being_id, []).append(entry)
                self._trace(
                    being_id, entry, "gave_up", attempts, tick, player_id, reason=failure
                )

    def undeliverable(self, being_id: BeingId) -> list[UndeliveredExpectationEvent]:
        """配り直しの上限に届き、この run では配らない出来事。"""
        return list(self._given_up.get(being_id, []))

    def _deliver(self, entry: UndeliveredExpectationEvent) -> str | None:
        for receiver in self._receivers:
            try:
                receiver.receive(entry.event_id, entry.event)
            except Exception as exc:
                # 受け取る側の失敗で清算のターンを止めない。未配信のまま残すので
                # 出来事は失われず、理由は trace に残る。
                logger.warning(
                    "expectation event %s was not received by %s",
                    entry.event_id,
                    type(receiver).__name__,
                    exc_info=True,
                )
                return f"{type(exc).__name__}: {exc}"
        return None

    def _trace(
        self,
        being_id: BeingId,
        entry: UndeliveredExpectationEvent,
        outcome: str,
        attempts: int,
        tick: int | None,
        player_id: int | None,
        *,
        reason: str | None = None,
    ) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        payload: dict[str, object] = {
            "being_id": being_id.value,
            "event_id": entry.event_id.value,
            "event_type": type(entry.event).__name__,
            "outcome": outcome,
            "attempts": attempts,
            "receiver_count": len(self._receivers),
        }
        if reason is not None:
            payload["reason"] = reason
        recorder.record(
            TraceEventKind.EXPECTATION_EVENT_DELIVERY,
            tick=tick,
            player_id=player_id,
            **payload,
        )


__all__ = ["ExpectationEventDispatcher", "ExpectationEventReceiver"]
