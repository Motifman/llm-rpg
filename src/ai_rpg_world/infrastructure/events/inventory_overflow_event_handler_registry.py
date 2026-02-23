"""インベントリ溢れ（満杯ドロップ）のイベントハンドラ登録"""

from typing import TYPE_CHECKING

from ai_rpg_world.application.world.handlers.inventory_overflow_drop_handler import InventoryOverflowDropHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.player.event.inventory_events import InventorySlotOverflowEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class InventoryOverflowEventHandlerRegistry:
    """InventorySlotOverflowEvent の同期ハンドラ登録（同一トランザクションでドロップをアトミックに扱う）"""

    def __init__(self, inventory_overflow_drop_handler: InventoryOverflowDropHandler):
        self._inventory_overflow_drop_handler = inventory_overflow_drop_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        event_publisher.register_handler(
            InventorySlotOverflowEvent,
            self._create_event_handler(self._inventory_overflow_drop_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
