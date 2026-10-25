from unittest.mock import Mock

from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.infrastructure.events.quest_event_handler_registry import QuestEventHandlerRegistry


def test_registry_subscribes_only_to_retained_events():
    """タイルとNPC会話のイベントを購読せず、残す3種をそれぞれ非同期の受け手に接続する。"""
    handlers = {name: Mock() for name in (
        "monster_died_handler", "player_downed_handler",
        "item_added_to_inventory_handler",
    )}
    publisher = Mock()
    QuestEventHandlerRegistry(**handlers).register_handlers(publisher)
    calls = publisher.register_handler.call_args_list
    assert {call.args[0] for call in calls} == {
        MonsterDiedEvent, PlayerDownedEvent, ItemAddedToInventoryEvent,
    }
    assert len(calls) == 3
    for call in calls:
        assert call.kwargs == {"is_synchronous": False}
    for call, name in zip(calls, (
        "monster_died_handler", "player_downed_handler",
        "item_added_to_inventory_handler",
    ), strict=True):
        event = Mock()
        call.args[1].handle(event)
        handlers[name].handle.assert_called_once_with(event)
