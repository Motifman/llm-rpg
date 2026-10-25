"""クエストの残った三つの登録と、確定後の配送を守る。"""

from unittest.mock import Mock

import pytest
from tests.support.command_scope_stack import CommandScopeTestStack

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee
from ai_rpg_world.infrastructure.events.quest_event_handler_registry import QuestEventHandlerRegistry
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


def test_registry_subscribes_only_to_retained_events() -> None:
    """残す三種だけを従来の順で確定後へ登録し、確定前の受け手は足さない。"""
    handlers = {name: Mock() for name in _NAMES}
    registrar = Mock()
    QuestEventHandlerRegistry(**handlers).register_command_handlers(registrar)
    calls = registrar.register_after_commit.call_args_list
    assert [entry.args[0] for entry in calls] == [MonsterDiedEvent, PlayerDownedEvent, ItemAddedToInventoryEvent]
    registrar.register_required_before_commit.assert_not_called()
    for entry, name in zip(calls, _NAMES, strict=True):
        assert entry.kwargs == {"channel": DeliveryChannel.INTEGRATION, "guarantee": DeliveryGuarantee.DURABLE_RETRY}
        event = Mock()
        entry.args[1](event)
        handlers[name].handle.assert_called_once_with(event)


_NAMES = ("monster_died_handler", "player_downed_handler", "item_added_to_inventory_handler")


def _events():
    return [
        MonsterDiedEvent.create(aggregate_id=MonsterId(1), aggregate_type="MonsterAggregate", respawn_tick=0, exp=1, gold=1, template_id=101, killer_player_id=PlayerId(1)),
        PlayerDownedEvent.create(aggregate_id=PlayerId(1), aggregate_type="PlayerStatusAggregate"),
        ItemAddedToInventoryEvent.create(aggregate_id=PlayerId(1), aggregate_type="PlayerInventoryAggregate", item_instance_id=ItemInstanceId(1)),
    ]


def _stack():
    store = InMemoryDataStore()
    scope = publisher = CommandScopeTestStack(store)
    handlers = {name: Mock() for name in _NAMES}
    QuestEventHandlerRegistry(**handlers).register_command_handlers(scope.dispatcher)
    return store, scope, publisher, handlers


@pytest.mark.parametrize("index", range(3))
def test_receiver_is_called_only_after_commit(index) -> None:
    """三つのイベントは対応する受け手だけへ渡り、保存の確定前には呼ばれない。"""
    _, scope, publisher, handlers = _stack()
    active = []
    handlers[_NAMES[index]].handle.side_effect = lambda event: active.append(scope.is_in_transaction())
    event = _events()[index]
    with scope:
        publisher.publish(event)
        assert not active
    assert active == [False]
    handlers[_NAMES[index]].handle.assert_called_once_with(event)
    assert all(not handler.mock_calls for name, handler in handlers.items() if name != _NAMES[index])


def test_batch_is_delivered_in_collection_order() -> None:
    """三種のイベントを集めた順に、対応する受け手を確定後に呼ぶ。"""
    _, scope, publisher, handlers = _stack()
    order = []
    for name, handler in handlers.items():
        handler.handle.side_effect = lambda event, name=name: order.append(name)
    events = _events()
    with scope:
        publisher.publish_all([events[2], events[0], events[1]])
    assert order == [_NAMES[2], _NAMES[0], _NAMES[1]]


def test_before_commit_failure_rolls_back_without_quest_delivery() -> None:
    """試験用の確定前処理が失敗すると状態を戻し、クエストの確定後処理を一つも呼ばない。"""
    store, scope, publisher, handlers = _stack()
    original = store.next_world_object_id

    def fail(event, context=None):
        raise RuntimeError("確定前の失敗")

    scope.dispatcher.register_required_before_commit(MonsterDiedEvent, fail)
    with pytest.raises(RuntimeError, match="確定前の失敗"):
        with scope:
            store.next_world_object_id = original + 1
            publisher.publish_all(_events())
    assert store.next_world_object_id == original
    assert all(not handler.mock_calls for handler in handlers.values())


@pytest.mark.parametrize("index", range(3))
def test_failure_is_traced_without_rollback_and_later_delivery_continues(index) -> None:
    """各受け手の失敗は保存を戻さず記録され、同じイベントの後続と後のイベントも試して例外を返す。"""
    from ai_rpg_world.application.common.exceptions import CommandPostCommitException
    from ai_rpg_world.domain.common.domain_event import DomainEvent

    store, scope, publisher, handlers = _stack()
    failure = RuntimeError("進捗の更新に失敗")
    handlers[_NAMES[index]].handle.side_effect = failure
    delivered = []
    scope.dispatcher.register_after_commit(DomainEvent, delivered.append, channel=DeliveryChannel.AUXILIARY, guarantee=DeliveryGuarantee.BEST_EFFORT)
    events = _events()
    changed = store.next_world_object_id + 1
    with pytest.raises(CommandPostCommitException) as caught:
        with scope:
            store.next_world_object_id = changed
            publisher.publish_all(events)
    assert store.next_world_object_id == changed
    assert delivered == events
    assert all(handler.handle.call_count == 1 for handler in handlers.values())
    assert caught.value.handoff_error is failure
    failures = scope.trace.of_kind("world_tick_unit_failed")
    assert len(failures) == 1
    assert failures[0].payload["target_id"] == type(events[index]).__name__
    assert failures[0].payload["error_message"] == "進捗の更新に失敗"
    assert failures[0].payload["continued"] is True
