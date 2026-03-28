"""Tests for UiEventHandlerRegistry."""

from unittest.mock import MagicMock

from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    SpotWeatherChangedEvent,
    WorldObjectMovedEvent,
)
from ai_rpg_world.infrastructure.events.ui_event_handler_registry import (
    UiEventHandlerRegistry,
)


def test_register_handlers_registers_expected_event_types():
    event_publisher = MagicMock()
    handler = MagicMock(spec=UiEventHandler)
    registry = UiEventHandlerRegistry(handler)

    registry.register_handlers(event_publisher)

    calls = event_publisher.register_handler.call_args_list
    assert len(calls) == 4
    registered = {call.args[0] for call in calls}
    assert registered == {
        PlayerLocationChangedEvent,
        WorldObjectMovedEvent,
        GatewayTriggeredEvent,
        SpotWeatherChangedEvent,
    }
    assert all(call.kwargs["is_synchronous"] is False for call in calls)

