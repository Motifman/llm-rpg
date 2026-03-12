"""ConsumableUsedEvent のイベントハンドラ登録"""

from typing import TYPE_CHECKING

from ai_rpg_world.application.world.handlers.consumable_effect_handler import ConsumableEffectHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class ConsumableEffectEventHandlerRegistry:
    """ConsumableUsedEvent の同期ハンドラ登録（効果を同一トランザクションで適用）"""

    def __init__(self, consumable_effect_handler: ConsumableEffectHandler):
        self._consumable_effect_handler = consumable_effect_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        event_publisher.register_handler(
            ConsumableUsedEvent,
            self._create_event_handler(self._consumable_effect_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
