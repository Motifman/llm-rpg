"""PlayerStatusAggregate の JSON コーデック round-trip 検証。"""

import pytest

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_codec import (
    json_bytes_to_player_status,
    player_status_to_json_bytes,
)


def _assert_status_equivalent(a: PlayerStatusAggregate, b: PlayerStatusAggregate) -> None:
    assert a.player_id == b.player_id
    assert a.base_stats == b.base_stats
    assert a.stat_growth_factor == b.stat_growth_factor
    assert a.exp_table == b.exp_table
    assert a.growth == b.growth
    assert a.gold == b.gold
    assert a.hp == b.hp
    assert a.mp == b.mp
    assert a.stamina == b.stamina
    assert a.is_down == b.is_down
    assert a.active_effects == b.active_effects
    assert a.attention_level == b.attention_level
    assert a.current_spot_id == b.current_spot_id


def _minimal_status(player_id: int = 1) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
    )


def test_player_status_json_roundtrip_minimal() -> None:
    orig = _minimal_status()
    blob = player_status_to_json_bytes(orig)
    restored = json_bytes_to_player_status(blob)
    _assert_status_equivalent(orig, restored)


def test_player_status_json_roundtrip_spot_and_effects() -> None:
    exp_table = ExpTable(120, 1.4, level_offset=0.5)
    nav = SpotId(3)
    effects = [
        StatusEffect(
            effect_type=StatusEffectType.POISON,
            value=0.9,
            expiry_tick=WorldTick(100),
        ),
        StatusEffect(
            effect_type=StatusEffectType.PARALYSIS,
            value=1.0,
            expiry_tick=WorldTick(200),
        ),
    ]
    orig = PlayerStatusAggregate(
        player_id=PlayerId(7),
        base_stats=BaseStats(20, 15, 12, 8, 9, 0.1, 0.2),
        stat_growth_factor=StatGrowthFactor(0.5, 0.5, 0.5, 0.5, 0.5, 0.02, 0.03),
        exp_table=exp_table,
        growth=Growth(3, 500, exp_table),
        gold=Gold(42),
        hp=Hp.create(30, 80),
        mp=Mp.create(10, 40),
        stamina=Stamina.create(5, 60),
        current_spot_id=nav,
        is_down=True,
        active_effects=effects,
        attention_level=AttentionLevel.FILTER_SOCIAL,
    )
    blob = player_status_to_json_bytes(orig)
    restored = json_bytes_to_player_status(blob)
    _assert_status_equivalent(orig, restored)


def test_old_json_discards_tile_navigation_and_pursuit():
    """旧JSONの座標・経路・追跡を読み捨て、現在地とHPを失わず新形式で再保存できる。"""
    import json

    data = json.loads(player_status_to_json_bytes(_minimal_status()))
    data.pop("current_spot_id", None)
    data["navigation_state"] = {
        "current_spot_id": 3,
        "current_coordinate": [1, 2, 0],
        "current_destination": [4, 5, 0],
        "planned_path": [[2, 2, 0]],
    }
    data["pursuit"] = {"actor_id": 1, "target_id": 99, "target_snapshot": None, "last_known": None}
    restored = json_bytes_to_player_status(json.dumps(data).encode())
    assert restored.current_spot_id == SpotId(3)
    assert restored.hp == _minimal_status().hp
    stored = json.loads(player_status_to_json_bytes(restored))
    assert "navigation_state" not in stored and "pursuit" not in stored
    assert not hasattr(restored, "_navigation_state") and not hasattr(restored, "_pursuit_state")


def test_json_rejects_missing_current_and_legacy_location():
    """新旧両方の現在地項目が欠けたJSONはKeyErrorで拒否し、現在地なしとして復元しない。"""
    import json

    data = json.loads(player_status_to_json_bytes(_minimal_status()))
    data.pop("current_spot_id")
    with pytest.raises(KeyError, match="navigation_state"):
        json_bytes_to_player_status(json.dumps(data).encode())
