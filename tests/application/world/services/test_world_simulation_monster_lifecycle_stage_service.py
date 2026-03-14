from types import SimpleNamespace
import unittest.mock as mock

from ai_rpg_world.application.world.services.world_simulation_monster_lifecycle_stage_service import (
    WorldSimulationMonsterLifecycleStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _build_stage(
    *,
    has_spawn_slot_support,
    has_hunger_migration_support,
    survival_coordinator=None,
):
    return WorldSimulationMonsterLifecycleStageService(
        world_time_config_service=mock.Mock(get_ticks_per_day=mock.Mock(return_value=24)),
        has_spawn_slot_support=lambda: has_spawn_slot_support,
        has_hunger_migration_support=lambda: has_hunger_migration_support,
        process_spawn_and_respawn_by_slots=mock.Mock(),
        process_respawn_legacy=mock.Mock(),
        survival_coordinator=survival_coordinator,
    )


def test_run_uses_slot_based_spawn_when_support_is_available():
    stage = _build_stage(
        has_spawn_slot_support=True,
        has_hunger_migration_support=False,
    )

    result = stage.run([], {SpotId(1)}, WorldTick(10))

    stage._process_spawn_and_respawn_by_slots.assert_called_once()
    stage._process_respawn_legacy.assert_not_called()
    assert result == set()


def test_run_falls_back_to_legacy_respawn_without_spawn_slot_support():
    stage = _build_stage(
        has_spawn_slot_support=False,
        has_hunger_migration_support=False,
    )

    result = stage.run([], {SpotId(1)}, WorldTick(10))

    stage._process_respawn_legacy.assert_called_once()
    stage._process_spawn_and_respawn_by_slots.assert_not_called()
    assert result == set()


def test_run_returns_empty_blocked_ids_when_survival_support_is_missing():
    stage = _build_stage(
        has_spawn_slot_support=True,
        has_hunger_migration_support=False,
    )

    result = stage.run(
        [SimpleNamespace(spot_id=SpotId(1))],
        {SpotId(1)},
        WorldTick(10),
    )

    assert result == set()


def test_run_dispatches_survival_only_for_active_spots_and_merges_blocked_ids():
    survival_coordinator = mock.Mock()
    map_a = SimpleNamespace(spot_id=SpotId(1))
    map_b = SimpleNamespace(spot_id=SpotId(2))
    blocked_a = {WorldObjectId(1)}
    blocked_b = {WorldObjectId(2)}
    survival_coordinator.process_survival_for_spot.side_effect = [blocked_a, blocked_b]
    stage = _build_stage(
        has_spawn_slot_support=True,
        has_hunger_migration_support=True,
        survival_coordinator=survival_coordinator,
    )

    result = stage.run([map_a, map_b], {SpotId(1), SpotId(2)}, WorldTick(10))

    assert result == blocked_a | blocked_b
    assert survival_coordinator.process_survival_for_spot.call_args_list == [
        mock.call(map_a, WorldTick(10)),
        mock.call(map_b, WorldTick(10)),
    ]


def test_run_skips_inactive_spots_when_dispatching_survival():
    survival_coordinator = mock.Mock()
    active_map = SimpleNamespace(spot_id=SpotId(1))
    inactive_map = SimpleNamespace(spot_id=SpotId(2))
    survival_coordinator.process_survival_for_spot.return_value = {WorldObjectId(1)}
    stage = _build_stage(
        has_spawn_slot_support=True,
        has_hunger_migration_support=True,
        survival_coordinator=survival_coordinator,
    )

    result = stage.run([active_map, inactive_map], {SpotId(1)}, WorldTick(10))

    assert result == {WorldObjectId(1)}
    survival_coordinator.process_survival_for_spot.assert_called_once_with(
        active_map,
        WorldTick(10),
    )

