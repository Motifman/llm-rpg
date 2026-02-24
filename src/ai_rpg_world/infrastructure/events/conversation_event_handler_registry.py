"""会話開始イベント（WorldObjectInteractedEvent TALK）のハンドラ登録"""

from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.world.event.map_events import WorldObjectInteractedEvent
from ai_rpg_world.application.conversation.handlers.conversation_start_handler import (
    ConversationStartHandler,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class ConversationEventHandlerRegistry:
    """会話関連イベントハンドラの登録（TALK で会話セッション開始）"""

    def __init__(self, conversation_start_handler: ConversationStartHandler):
        self._conversation_start_handler = conversation_start_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        event_publisher.register_handler(
            WorldObjectInteractedEvent,
            self._create_event_handler(self._conversation_start_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
