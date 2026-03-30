"""Tests for the demo web database seeding helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.presentation.web.demo_seed import (
    DEFAULT_WEB_GAME_DB,
    main,
    seed_demo_world_database,
)
from ai_rpg_world.presentation.web.runtime import SqliteWebAppConfig, create_sqlite_web_runtime


def test_seed_demo_world_database_creates_reusable_runtime(tmp_path: Path) -> None:
    database = tmp_path / "demo.db"

    path = seed_demo_world_database(database)
    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(database_path=path, manual_player_ids=(1,))
    )
    try:
        snapshot_one = runtime.projection.get_snapshot(1)
        snapshot_two = runtime.projection.get_snapshot(2)

        assert path == database.resolve()
        assert snapshot_one.spot_name == "Starter Town"
        assert snapshot_one.actors[0].display_name == "Hero"
        assert snapshot_one.monsters[0].display_name == "Slime"
        assert snapshot_one.monsters[0].tile_x == 12
        assert snapshot_one.monsters[0].tile_y == 11
        assert snapshot_one.objects[0].display_name == "宝箱"
        assert snapshot_one.objects[0].interaction_type == "open_chest"
        assert snapshot_one.objects[0].interaction_data["is_open"] is False
        assert snapshot_one.map.map_width_tiles == 16
        assert snapshot_one.map.map_height_tiles == 16
        assert snapshot_two.spot_name == "South Gate"
        assert snapshot_two.weather is not None
        assert snapshot_two.weather.weather_type == "RAIN"
        assert snapshot_one.gateways[0].tile_x == 8
        assert snapshot_one.gateways[0].tile_y == 1
        assert snapshot_one.gateways[0].landing_tile_x == 6
        assert snapshot_one.gateways[0].landing_tile_y == 9
        assert snapshot_two.gateways[0].tile_x == 6
        assert snapshot_two.gateways[0].tile_y == 10
        world_state = runtime.container.get_world_state_repositories()
        physical_map = world_state.world_runtime.physical_maps.find_by_id(SpotId(1))
        assert physical_map is not None
        assert (
            physical_map.is_passable(
                Coordinate(4, 5, 0),
                MovementCapability.normal_walk(),
            )
            is False
        )
    finally:
        runtime.close()


def test_seed_demo_world_database_uses_tiled_collision_as_source_of_truth(
    tmp_path: Path,
) -> None:
    database = tmp_path / "demo.db"
    path = seed_demo_world_database(database)
    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(database_path=path, manual_player_ids=(1,))
    )
    try:
        world_state = runtime.container.get_world_state_repositories()
        physical_map = world_state.world_runtime.physical_maps.find_by_id(SpotId(1))
        assert physical_map is not None

        map_path = (
            Path(__file__).resolve().parents[3]
            / "frontend"
            / "public"
            / "data"
            / "maps"
            / "spot_1.json"
        )
        tiled = json.loads(map_path.read_text(encoding="utf-8"))
        collision_layer = next(
            layer
            for layer in tiled["layers"]
            if layer.get("type") == "tilelayer" and layer.get("name") == "collision"
        )
        width = int(tiled["width"])
        height = int(tiled["height"])
        collision_data = collision_layer["data"]

        capability = MovementCapability.normal_walk()
        for y in range(height):
            for x in range(width):
                gid = collision_data[(y * width) + x]
                tile = physical_map.get_tile(Coordinate(x, y, 0))
                expected_passable = gid == 0
                actual_passable = tile.terrain_type.can_pass(capability)
                assert actual_passable is expected_passable
    finally:
        runtime.close()


def test_seed_demo_world_database_raises_when_existing_without_overwrite(
    tmp_path: Path,
) -> None:
    database = tmp_path / "demo.db"
    database.write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        seed_demo_world_database(database)


def test_seed_demo_world_database_overwrites_existing_file(tmp_path: Path) -> None:
    database = tmp_path / "demo.db"
    database.write_text("occupied", encoding="utf-8")

    seed_demo_world_database(database, overwrite=True)

    connection = sqlite3.connect(str(database))
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM game_spots"
        ).fetchone()
        assert row is not None
        assert row[0] == 2
        stamina_row = connection.execute(
            "SELECT stamina_value, stamina_max FROM game_player_statuses WHERE player_id = 1"
        ).fetchone()
        assert stamina_row is not None
        assert stamina_row[0] == 1_000_000
        assert stamina_row[1] == 1_000_000
    finally:
        connection.close()


def test_main_uses_default_path_when_no_arguments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main([])

    assert exit_code == 0
    assert (tmp_path / DEFAULT_WEB_GAME_DB).exists()
