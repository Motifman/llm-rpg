"""観測用イベントハンドラを EventPublisher に登録する Registry"""

from ai_rpg_world.application.observation.handlers.observation_event_handler import ObservationEventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLocationChangedEvent,
    PlayerDownedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)

# 観測対象イベント型一覧（仕様に基づく）
_OBSERVED_EVENT_TYPES = (
    GatewayTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    PlayerLocationChangedEvent,
    PlayerDownedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)


class ObservationEventHandlerRegistry:
    """観測用ハンドラを全観測対象イベント型に登録する"""

    def __init__(self, observation_handler: ObservationEventHandler) -> None:
        self._handler = observation_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全観測対象イベント型に対して同一ハンドラを非同期で登録する"""
        for event_type in _OBSERVED_EVENT_TYPES:
            event_publisher.register_handler(
                event_type,
                self._handler,
                is_synchronous=False,
            )
