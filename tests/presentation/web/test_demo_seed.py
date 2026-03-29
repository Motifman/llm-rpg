"""Tests for the demo web database seeding helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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
        assert snapshot_one.map.map_width_tiles == 10
        assert snapshot_one.map.map_height_tiles == 10
        assert snapshot_two.spot_name == "South Gate"
        assert snapshot_two.weather is not None
        assert snapshot_two.weather.weather_type == "RAIN"
        assert snapshot_one.gateways[0].landing_tile_x == 2
        assert snapshot_one.gateways[0].landing_tile_y == 7
        assert snapshot_two.gateways[0].tile_x == 2
        assert snapshot_two.gateways[0].tile_y == 8
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
