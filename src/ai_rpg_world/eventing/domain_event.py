import itertools
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypedDict

_sequences = itertools.count(1)
_sequence_lock = threading.Lock()


def _next_sequence() -> int:
    with _sequence_lock:
        return next(_sequences)


@dataclass(frozen=True)
class DomainEvent:
    event_id: int
    occurred_at: datetime
    # 印を通さずに作られるイベントとも出た順を比べられるよう、既定値を印と同じ数え器から取る (#2086)。
    # outbox から復元すると番号は振り直されるので、等しさには含めない。
    sequence: int = field(default_factory=_next_sequence, kw_only=True, compare=False)


class EventStamp(TypedDict):
    event_id: int
    occurred_at: datetime
    sequence: int


def new_event_stamp() -> EventStamp:
    # 観測の流れで occurred_at どうしを比べるので、タイムゾーン無しの日時が混ざると TypeError になる (#311)。
    return {"event_id": uuid.uuid4().int, "occurred_at": datetime.now(timezone.utc), "sequence": _next_sequence()}
