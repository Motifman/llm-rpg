from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick


class TestBaseDomainEvent:
    def test_create_accepts_occurred_tick(self):
        event = BaseDomainEvent.create(
            aggregate_id=1,
            aggregate_type="TestAggregate",
            occurred_tick=WorldTick(42),
        )
        assert event.occurred_tick == WorldTick(42)


def test_game_event_inherits_common_event() -> None:
    """ゲームのイベントは、共通のイベントの一種として扱える。"""
    from ai_rpg_world.eventing import DomainEvent

    assert issubclass(BaseDomainEvent, DomainEvent)


def test_domain_event_alias_is_common_event() -> None:
    """ゲーム側から DomainEvent を読み込むと、共通の基底と同じ型を指す。"""
    from ai_rpg_world.domain.common.domain_event import DomainEvent
    from ai_rpg_world.eventing import DomainEvent as CommonDomainEvent

    assert DomainEvent is CommonDomainEvent


def test_game_event_keeps_positional_fields() -> None:
    """ゲームのイベントは、識別子・日時・集約 ID・集約の種類の順に位置引数を受け取る。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    event = BaseDomainEvent(7, now, 42, "TestAggregate")
    assert (event.event_id, event.occurred_at, event.aggregate_id, event.aggregate_type) == (
        7, now, 42, "TestAggregate"
    )
    assert event.occurred_tick is None


def test_create_uses_uuid_integer() -> None:
    """create は、生成した UUID の整数値をイベントの識別子に使う。"""
    from unittest.mock import patch
    from uuid import UUID

    expected = UUID("cafebab0-1234-4123-8123-0123456789ab")
    with patch("ai_rpg_world.domain.common.domain_event.uuid.uuid4", return_value=expected):
        event = BaseDomainEvent.create(1, "TestAggregate")
    assert event.event_id == expected.int


def test_create_uses_timezone_aware_utc() -> None:
    """create は、タイムゾーン付きの UTC 日時で発生時刻を記録する。"""
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc)
    event = BaseDomainEvent.create(1, "TestAggregate")
    after = datetime.now(timezone.utc)
    assert event.occurred_at.tzinfo is timezone.utc
    assert before <= event.occurred_at <= after
