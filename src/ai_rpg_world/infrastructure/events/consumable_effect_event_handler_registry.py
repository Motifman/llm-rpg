"""ConsumableUsedEvent のイベントハンドラ登録"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.common.event_delivery import CommandEventHandlerRegistrarPort
from ai_rpg_world.application.world.handlers.consumable_effect_handler import ConsumableEffectHandler
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class ConsumableEffectEventHandlerRegistry:
    """ConsumableUsedEvent の同期ハンドラ登録（効果を同一トランザクションで適用）"""

    def __init__(self, consumable_effect_handler: ConsumableEffectHandler):
        self._consumable_effect_handler = consumable_effect_handler

    def register_handlers(self, event_publisher: EventPublisher[DomainEvent]) -> None:
        event_publisher.register_handler(
            ConsumableUsedEvent,
            self._create_event_handler(self._consumable_effect_handler.handle),
            is_synchronous=True,
        )

    def register_command_handlers(self, registrar: CommandEventHandlerRegistrarPort) -> None:
        """既存のイベント対応を、確定の前後を保って共通基盤へ登録する。"""
        registrar.register_required_before_commit(
            ConsumableUsedEvent, lambda event, _context: self._consumable_effect_handler.handle(event),
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
