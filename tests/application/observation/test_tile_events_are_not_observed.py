"""退役したタイルの出来事は型を残さず、現行の天候イベントだけを維持する。"""

from importlib import import_module

import pytest


def test_retired_monster_feed_event_is_absent() -> None:
    """タイル上の採食イベントは、発行元の退役後に型の定義も残さない。"""
    module = import_module("ai_rpg_world.domain.monster.event.monster_events")
    assert not hasattr(module, "MonsterFedEvent")


def test_retired_map_events_are_absent() -> None:
    """退役したマップのイベントは定義されず、天候変化のイベントだけが残る。"""
    module = import_module("ai_rpg_world.domain.world.event.map_events")
    assert {name for name in vars(module) if name.endswith("Event")} == {
        "BaseDomainEvent", "SpotWeatherChangedEvent",
    }
    with pytest.raises(ModuleNotFoundError):
        import_module("ai_rpg_world.domain.world.event.harvest_events")
