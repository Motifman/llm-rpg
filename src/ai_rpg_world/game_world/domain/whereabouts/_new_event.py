from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypeVar

from ai_rpg_world.eventing import DomainEvent

_Event = TypeVar("_Event", bound=DomainEvent)


def new_event(kind: type[_Event], **fields: Any) -> _Event:
    return kind(event_id=uuid.uuid4().int, occurred_at=datetime.now(timezone.utc), **fields)
