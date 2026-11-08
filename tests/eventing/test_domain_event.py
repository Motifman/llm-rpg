"""共通のイベントは、文脈に依存しない識別子と発生日時を保持する。"""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest

from ai_rpg_world.eventing import DomainEvent, new_event_stamp


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


def test_new_event_stamp_gives_utc_aware_time() -> None:
    """new_event_stamp の日時は UTC のタイムゾーン付きで、タイムゾーン無しの日時と混ざらない。"""
    stamp = new_event_stamp()

    assert stamp["occurred_at"].tzinfo is timezone.utc


def test_new_event_stamp_gives_a_new_id_each_time() -> None:
    """new_event_stamp を続けて呼ぶと、呼ぶたびに違う識別子を返す。"""
    first = new_event_stamp()
    second = new_event_stamp()

    assert first["event_id"] != second["event_id"]


def test_new_event_stamp_fills_the_event_fields() -> None:
    """new_event_stamp の中身をそのまま渡すと、識別子と日時を持つイベントが作れる。"""
    stamp = new_event_stamp()

    event = DomainEvent(**stamp)

    assert (event.event_id, event.occurred_at) == (stamp["event_id"], stamp["occurred_at"])
