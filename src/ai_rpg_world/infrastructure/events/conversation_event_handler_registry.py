"""会話開始イベント（WorldObjectInteractedEvent TALK）のハンドラ登録"""

from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.application.conversation.handlers.conversation_start_handler import (
    ConversationStartHandler,
)
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.world.event.map_events import WorldObjectInteractedEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class ConversationEventHandlerRegistry:
    """会話関連イベントハンドラの登録（TALK で会話セッション開始）"""

    def __init__(self, conversation_start_handler: ConversationStartHandler):
        self._conversation_start_handler = conversation_start_handler

    def register_handlers(self, event_publisher: EventPublisher[DomainEvent]) -> None:
        event_publisher.register_handler(
            WorldObjectInteractedEvent,
            self._create_event_handler(self._conversation_start_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler[Any]":
        class EventHandlerImpl(EventHandler[Any]):
            def __init__(self, method: Callable[[Any], None]) -> None:
                self._method = method

            def handle(self, event: Any) -> None:
                self._method(event)

        return EventHandlerImpl(handler_method)
