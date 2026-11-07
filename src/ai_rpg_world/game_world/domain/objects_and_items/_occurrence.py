from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def occurrence() -> dict[str, Any]:
    return {"event_id": uuid.uuid4().int, "occurred_at": datetime.now(timezone.utc)}
