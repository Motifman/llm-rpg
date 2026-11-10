"""共通のイベントは、文脈に依存しない識別子と発生日時と、出た順を比べる通し番号を保持する。"""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest

from ai_rpg_world.eventing import DomainEvent, new_event_stamp


def test_event_has_only_identity_timestamp_and_sequence() -> None:
    """共通のイベントを作ると、識別子と日時と通し番号だけを指定したまま保持する。"""
    now = datetime.now(timezone.utc)
    event = DomainEvent(123, now, sequence=7)
    assert [field.name for field in fields(event)] == ["event_id", "occurred_at", "sequence"]
    assert (event.event_id, event.occurred_at, event.sequence) == (123, now, 7)


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

    assert (event.event_id, event.occurred_at, event.sequence) == (
        stamp["event_id"],
        stamp["occurred_at"],
        stamp["sequence"],
    )


def test_later_stamp_has_larger_sequence() -> None:
    """new_event_stamp を続けて 2 回呼ぶと、あとに作った印の通し番号のほうが大きい。"""
    first = new_event_stamp()
    second = new_event_stamp()

    assert first["sequence"] < second["sequence"]


def test_events_compare_their_order_by_sequence() -> None:
    """別々の印から作った 2 つのイベントは、通し番号で先に出たほうを見分けられる。"""
    earlier = DomainEvent(**new_event_stamp())
    later = DomainEvent(**new_event_stamp())

    assert sorted([later, earlier], key=lambda event: event.sequence) == [earlier, later]


def test_stamped_and_unstamped_events_are_numbered_in_creation_order() -> None:
    """印で作ったイベントと印を通さずに作ったイベントを交互に作ると、作った順に通し番号が大きくなる。"""
    first = DomainEvent(**new_event_stamp())
    second = DomainEvent(1, datetime.now(timezone.utc))
    third = DomainEvent(**new_event_stamp())

    assert first.sequence < second.sequence < third.sequence


def test_events_differing_only_in_sequence_are_equal() -> None:
    """識別子と日時が同じで通し番号だけが違う 2 つのイベントは、等しいと判定される。"""
    now = datetime.now(timezone.utc)

    assert DomainEvent(123, now, sequence=1) == DomainEvent(123, now, sequence=2)
