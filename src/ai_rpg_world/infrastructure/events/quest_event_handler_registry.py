from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.world.event.map_events import ItemTakenFromChestEvent
from ai_rpg_world.application.quest.handlers.quest_progress_handler import (
    QuestProgressHandler,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class QuestEventHandlerRegistry:
    """クエスト関連イベントハンドラの登録"""

    def __init__(self, quest_progress_handler: QuestProgressHandler):
        self._quest_progress_handler = quest_progress_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全イベントハンドラを EventPublisher に登録（非同期）"""
        event_publisher.register_handler(
            MonsterDiedEvent,
            self._create_event_handler(self._quest_progress_handler.handle),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            PlayerDownedEvent,
            self._create_event_handler(
                self._quest_progress_handler.handle_player_downed
            ),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            ItemTakenFromChestEvent,
            self._create_event_handler(
                self._quest_progress_handler.handle_item_taken_from_chest
            ),
            is_synchronous=False,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
