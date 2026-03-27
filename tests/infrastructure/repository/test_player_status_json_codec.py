"""PlayerStatusAggregate の JSON コーデック round-trip 検証。"""

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
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_pursuit_state import PlayerPursuitState
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import PursuitLastKnownState
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import PursuitTargetSnapshot
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
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
    assert a._navigation_state == b._navigation_state
    assert a._pursuit_state == b._pursuit_state


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


def test_player_status_json_roundtrip_rich_navigation_and_effects() -> None:
    exp_table = ExpTable(120, 1.4, level_offset=0.5)
    nav = PlayerNavigationState.from_parts(
        current_spot_id=SpotId(3),
        current_coordinate=Coordinate(1, 2, 0),
        current_destination=Coordinate(4, 5, 1),
        planned_path=(Coordinate(1, 2, 0), Coordinate(2, 2, 0)),
        goal_destination_type="location",
        goal_spot_id=SpotId(3),
        goal_location_area_id=None,
        goal_world_object_id=WorldObjectId(99),
    )
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
        navigation_state=nav,
        is_down=True,
        active_effects=effects,
        attention_level=AttentionLevel.FILTER_SOCIAL,
    )
    blob = player_status_to_json_bytes(orig)
    restored = json_bytes_to_player_status(blob)
    _assert_status_equivalent(orig, restored)


def test_player_status_json_roundtrip_with_pursuit() -> None:
    exp_table = ExpTable(100, 1.5)
    snap = PursuitTargetSnapshot(
        target_id=WorldObjectId(10),
        spot_id=SpotId(2),
        coordinate=Coordinate(3, 4, 0),
    )
    last_known = PursuitLastKnownState(
        target_id=WorldObjectId(10),
        spot_id=SpotId(2),
        coordinate=Coordinate(3, 4, 0),
        observed_at_tick=WorldTick(55),
    )
    started = PlayerPursuitState.empty().with_started(
        actor_id=WorldObjectId(1),
        target_id=WorldObjectId(10),
        target_snapshot=snap,
        last_known=last_known,
    )
    assert started.pursuit is not None
    with_failure = PursuitState(
        actor_id=started.pursuit.actor_id,
        target_id=started.pursuit.target_id,
        target_snapshot=started.pursuit.target_snapshot,
        last_known=started.pursuit.last_known,
        failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
    )
    orig = PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp.create(10, 10),
        mp=Mp.create(10, 10),
        stamina=Stamina.create(10, 10),
        pursuit_state=PlayerPursuitState.from_parts(pursuit=with_failure),
    )
    blob = player_status_to_json_bytes(orig)
    restored = json_bytes_to_player_status(blob)
    _assert_status_equivalent(orig, restored)
