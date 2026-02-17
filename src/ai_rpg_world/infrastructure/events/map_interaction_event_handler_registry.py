"""マップオブジェクト相互作用（チェスト・ドア等）のイベントハンドラ登録"""

from typing import TYPE_CHECKING

from ai_rpg_world.application.world.handlers.item_stored_in_chest_handler import ItemStoredInChestHandler
from ai_rpg_world.application.world.handlers.item_taken_from_chest_handler import ItemTakenFromChestHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.world.event.map_events import ItemStoredInChestEvent, ItemTakenFromChestEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class MapInteractionEventHandlerRegistry:
    """マップオブジェクト相互作用関連イベントハンドラの登録"""

    def __init__(
        self,
        item_stored_in_chest_handler: ItemStoredInChestHandler,
        item_taken_from_chest_handler: ItemTakenFromChestHandler,
    ):
        self._item_stored_in_chest_handler = item_stored_in_chest_handler
        self._item_taken_from_chest_handler = item_taken_from_chest_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        event_publisher.register_handler(
            ItemStoredInChestEvent,
            self._create_event_handler(self._item_stored_in_chest_handler.handle),
            is_synchronous=True,
        )
        event_publisher.register_handler(
            ItemTakenFromChestEvent,
            self._create_event_handler(self._item_taken_from_chest_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
