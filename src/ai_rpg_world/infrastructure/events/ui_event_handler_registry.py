"""Registers UI-facing event handler for selected domain events."""

from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    SpotWeatherChangedEvent,
    WorldObjectMovedEvent,
)


class UiEventHandlerRegistry:
    def __init__(self, handler: UiEventHandler) -> None:
        self._handler = handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        for event_type in (
            PlayerLocationChangedEvent,
            WorldObjectMovedEvent,
            GatewayTriggeredEvent,
            SpotWeatherChangedEvent,
        ):
            event_publisher.register_handler(
                event_type,
                self._handler,
                is_synchronous=False,
            )
