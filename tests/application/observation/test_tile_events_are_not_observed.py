"""退役したタイルの出来事が、観測登録や文面に戻らないことを保証する。"""

from importlib import import_module
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import ObservedEventRegistry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.events.observation_event_handler_registry import _OBSERVED_EVENT_TYPES

_TILE_EVENT_GROUPS = {
    "monster.event.monster_events": (
        "MonsterDecidedToMoveEvent", "MonsterDecidedToUseSkillEvent",
        "MonsterDecidedToInteractEvent", "MonsterFedEvent",
    ),
}
_TILE_EVENTS = [
    getattr(import_module(f"ai_rpg_world.domain.{module}"), name)
    for module, names in _TILE_EVENT_GROUPS.items()
    for name in names
]


@pytest.mark.parametrize("event_type", _TILE_EVENTS, ids=lambda t: t.__name__)
def test_tile_event_has_no_observation_registration(event_type: type) -> None:
    """タイル専用の出来事は、本番と旧購読のどちらの観測登録にも含まれない。"""
    registry = ObservedEventRegistry()
    event = event_type.__new__(event_type)
    assert not registry.is_observed(event)
    assert registry.get_strategy_for_event(event) is None
    assert event_type not in _OBSERVED_EVENT_TYPES


@pytest.mark.parametrize("event_type", _TILE_EVENTS, ids=lambda t: t.__name__)
def test_tile_event_has_no_recipients(event_type: type) -> None:
    """タイル専用の出来事を受け取っても、観測の配信先を作らない。"""
    resolver = create_observation_recipient_resolver(MagicMock())
    assert resolver.resolve(event_type.__new__(event_type)) == []


@pytest.mark.parametrize("event_type", _TILE_EVENTS, ids=lambda t: t.__name__)
def test_tile_event_has_no_prose(event_type: type) -> None:
    """タイル専用の出来事を直接整形しても、観測文を作らない。"""
    assert ObservationFormatter().format(event_type.__new__(event_type), PlayerId(1)) is None


def test_retired_map_events_are_absent() -> None:
    """退役したマップのイベントは定義されず、天候変化のイベントだけが残る。"""
    module = import_module("ai_rpg_world.domain.world.event.map_events")
    assert {name for name in vars(module) if name.endswith("Event")} == {
        "BaseDomainEvent", "SpotWeatherChangedEvent",
    }
    with pytest.raises(ModuleNotFoundError):
        import_module("ai_rpg_world.domain.world.event.harvest_events")
