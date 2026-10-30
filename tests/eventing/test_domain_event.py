"""共通のイベントは、文脈に依存しない識別子と発生日時を保持する。"""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest

from ai_rpg_world.eventing import DomainEvent


def test_event_has_only_identity_and_timestamp() -> None:
    """共通のイベントを作ると、識別子と日時だけを指定したまま保持する。"""
    now = datetime.now(timezone.utc)
    event = DomainEvent(123, now)
    assert [field.name for field in fields(event)] == ["event_id", "occurred_at"]
    assert (event.event_id, event.occurred_at) == (123, now)


def test_event_cannot_be_changed() -> None:
    """作成済みのイベントの識別子を書き換えようとすると拒否する。"""
    event = DomainEvent(123, datetime.now(timezone.utc))
    with pytest.raises(FrozenInstanceError):
        event.event_id = 456
