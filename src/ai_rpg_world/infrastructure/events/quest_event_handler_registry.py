from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.quest.handlers.quest_progress_handler import (
    ConversationEndedQuestProgressHandler,
    ItemAddedToInventoryQuestProgressHandler,
    MonsterDiedQuestProgressHandler,
    PlayerDownedQuestProgressHandler,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
)
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class QuestEventHandlerRegistry:
    """クエスト関連イベントハンドラの登録"""

    def __init__(
        self,
        monster_died_handler: MonsterDiedQuestProgressHandler,
        player_downed_handler: PlayerDownedQuestProgressHandler,
        item_added_to_inventory_handler: ItemAddedToInventoryQuestProgressHandler,
        conversation_ended_handler: ConversationEndedQuestProgressHandler,
    ):
        self._monster_died_handler = monster_died_handler
        self._player_downed_handler = player_downed_handler
        self._item_added_to_inventory_handler = item_added_to_inventory_handler
        self._conversation_ended_handler = conversation_ended_handler

    def register_handlers(self, event_publisher: EventPublisher[DomainEvent]) -> None:
        """全イベントハンドラを EventPublisher に登録（非同期）"""
        event_publisher.register_handler(
            MonsterDiedEvent,
            self._create_event_handler(self._monster_died_handler.handle),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            PlayerDownedEvent,
            self._create_event_handler(self._player_downed_handler.handle),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            ItemAddedToInventoryEvent,
            self._create_event_handler(self._item_added_to_inventory_handler.handle),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            ConversationEndedEvent,
            self._create_event_handler(self._conversation_ended_handler.handle),
            is_synchronous=False,
        )

    def _create_event_handler(
        self, handler_method: Callable[[Any], None]
    ) -> "EventHandler[Any]":
        class EventHandlerImpl(EventHandler[Any]):
            def __init__(self, method: Callable[[Any], None]) -> None:
                self._method = method

            def handle(self, event: Any) -> None:
                self._method(event)

        return EventHandlerImpl(handler_method)
