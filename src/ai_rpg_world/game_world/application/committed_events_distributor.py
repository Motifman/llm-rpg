from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, final

from ai_rpg_world.eventing import DomainEvent, EventHandler
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException

_Event = TypeVar("_Event", bound=DomainEvent)


class CommittedEventsReceiver(Protocol):
    def receive(self, events: tuple[DomainEvent, ...]) -> None: ...


@final
@dataclass(frozen=True)
class _HandlerRegistration:
    event_type: type[DomainEvent]
    handler: EventHandler[Any]


@final
class CommittedEventsDistributor:
    def __init__(self) -> None:
        self._receivers: list[CommittedEventsReceiver] = []
        self._registrations: list[_HandlerRegistration] = []
        self._waiting: deque[tuple[DomainEvent, ...]] = deque()
        self._distributing = False
        self._refused_handlers: Counter[tuple[str, str]] = Counter()

    @property
    def refused_handlers(self) -> Mapping[tuple[str, str], int]:
        return dict(self._refused_handlers)

    def register_receiver(self, receiver: CommittedEventsReceiver) -> None:
        self._receivers.append(receiver)

    def register_handler(self, event_type: type[_Event], handler: EventHandler[_Event]) -> None:
        self._registrations.append(_HandlerRegistration(event_type, handler))

    def distribute(self, events: Sequence[DomainEvent]) -> None:
        if not events:
            return
        self._waiting.append(tuple(events))
        # ハンドラの範囲が確定して呼び戻されたときは、待たせて今の世代を配り終えてから配る。
        # 先に配ると、同じイベントを受けるほかのハンドラより先に、その結果への反応が動き、登録の順で結果が変わる。
        if self._distributing:
            return
        self._distributing = True
        try:
            while self._waiting:
                self._hand_over(self._waiting.popleft())
        finally:
            self._distributing = False
            self._waiting.clear()

    def _hand_over(self, batch: tuple[DomainEvent, ...]) -> None:
        for receiver in self._receivers:
            receiver.receive(batch)
        for event in batch:
            for registration in self._registrations:
                if isinstance(event, registration.event_type):
                    self._run_handler(registration.handler, event)

    def _run_handler(self, handler: EventHandler[Any], event: DomainEvent) -> None:
        try:
            handler.handle(event)
        except GameWorldDomainException as refusal:
            self._refused_handlers[(type(handler).__name__, refusal.error_code)] += 1
