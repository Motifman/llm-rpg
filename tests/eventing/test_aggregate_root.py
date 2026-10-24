"""共通の集約の基底は、未発行のイベントを自身にためる。"""

from datetime import datetime, timezone

from ai_rpg_world.eventing import AggregateRoot, DomainEvent


def test_events_are_kept_in_added_order() -> None:
    """空の集約に二つのイベントを追加すると、追加順に取得できる。"""
    aggregate = AggregateRoot[DomainEvent]()
    events = [DomainEvent(i, datetime.now(timezone.utc)) for i in (1, 2)]
    for event in events:
        assert aggregate.add_event(event) is None
    assert aggregate.get_events() == events


def test_changing_returned_events_does_not_change_aggregate() -> None:
    """取得した一覧を消去しても、集約が保持するイベントは残る。"""
    aggregate = AggregateRoot[DomainEvent]()
    event = DomainEvent(1, datetime.now(timezone.utc))
    aggregate.add_event(event)
    aggregate.get_events().clear()
    assert aggregate.get_events() == [event]


def test_clear_removes_only_own_events() -> None:
    """一方の集約を空にしても、別の集約と取得済みの一覧のイベントは残る。"""
    first = AggregateRoot[DomainEvent]()
    second = AggregateRoot[DomainEvent]()
    event = DomainEvent(1, datetime.now(timezone.utc))
    first.add_event(event)
    second.add_event(event)
    retrieved = first.get_events()
    assert first.clear_events() is None
    assert first.get_events() == []
    assert second.get_events() == [event]
    assert retrieved == [event]


def test_game_aggregate_inherits_event_buffer() -> None:
    """ゲームの集約は、共通の基底でイベントをためる。"""
    from ai_rpg_world.domain.common.aggregate_root import AggregateRoot as GameAggregateRoot

    assert issubclass(GameAggregateRoot, AggregateRoot)
