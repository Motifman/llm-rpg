"""退役したタイルの出来事は型も専用モジュールも残さない。"""

from importlib import import_module

import pytest


def test_retired_monster_feed_event_is_absent() -> None:
    """タイル上の採食イベントは、発行元の退役後に型の定義も残さない。"""
    module = import_module("ai_rpg_world.domain.monster.event.monster_events")
    assert not hasattr(module, "MonsterFedEvent")


def test_retired_map_events_are_absent() -> None:
    """退役したマップのイベントと採取のモジュールは読み込めない。"""
    with pytest.raises(ModuleNotFoundError):
        import_module("ai_rpg_world.domain.world.event.map_events")
    with pytest.raises(ModuleNotFoundError):
        import_module("ai_rpg_world.domain.world.event.harvest_events")
