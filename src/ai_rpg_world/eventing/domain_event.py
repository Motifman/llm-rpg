import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict


@dataclass(frozen=True)
class DomainEvent:
    event_id: int
    occurred_at: datetime


class EventStamp(TypedDict):
    event_id: int
    occurred_at: datetime


def new_event_stamp() -> EventStamp:
    # 観測の流れで occurred_at どうしを比べるので、タイムゾーン無しの日時が混ざると TypeError になる (#311)。
    return {"event_id": uuid.uuid4().int, "occurred_at": datetime.now(timezone.utc)}
