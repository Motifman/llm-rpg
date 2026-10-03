from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationDismissed,
    ExpectationEvent,
    ExpectationExpired,
    ExpectationSettled,
    ExpectationVoided,
    ProvisionallyMissed,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)

_EVENT_TYPES = (
    ProvisionallyMissed,
    ExpectationSettled,
    ExpectationDismissed,
    ExpectationVoided,
    ExpectationExpired,
)


@dataclass(frozen=True)
class UndeliveredExpectationEvent:
    """まだ配信していない、予期の集約が返した出来事。"""

    event_id: ExpectationEventId
    event: ExpectationEvent

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, ExpectationEventId):
            raise ExpectationValidationException(
                "event_id must be ExpectationEventId"
            )
        if not isinstance(self.event, _EVENT_TYPES):
            raise ExpectationValidationException("event must be ExpectationEvent")

    @classmethod
    def of(cls, event: ExpectationEvent) -> UndeliveredExpectationEvent:
        """予期の ID とターンから ID を作る。

        1 つの予期は 1 ターンに出来事を 1 つまでしか返さないので、この組で決まる。
        同じ出来事を配り直しても同じ ID になり、受け取る側が重複を見分けられる。
        """
        if not isinstance(event, _EVENT_TYPES):
            raise ExpectationValidationException("event must be ExpectationEvent")
        return cls(
            event_id=ExpectationEventId(f"{event.expectation_id}@{event.turn}"),
            event=event,
        )


__all__ = ["UndeliveredExpectationEvent"]
