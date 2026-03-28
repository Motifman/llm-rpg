"""Integration-style tests for SQLite-backed web runtime composition."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from ai_rpg_world.presentation.web.demo_seed import (
    seed_demo_world_database,
)
from ai_rpg_world.presentation.web.runtime import (
    SqliteWebAppConfig,
    create_sqlite_web_runtime,
)


def test_create_sqlite_web_runtime_bootstraps_projection_from_sqlite(tmp_path: Path):
    database = tmp_path / "runtime.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
        )
    )
    try:
        client = TestClient(runtime.app)

        response = client.get("/api/scenes/1/snapshot")
        overview_response = client.get("/api/world/overview")

        assert response.status_code == 200
        payload = response.json()
        assert payload["spot_name"] == "Starter Town"
        assert payload["actors"][0]["display_name"] == "Hero"
        assert payload["actors"][0]["is_manual_controlled"] is True
        assert overview_response.status_code == 200
        assert len(overview_response.json()) == 2
    finally:
        runtime.close()


def test_sqlite_web_runtime_move_endpoint_updates_projection_and_database(tmp_path: Path):
    database = tmp_path / "runtime.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
        )
    )
    try:
        client = TestClient(runtime.app)

        move_response = client.post("/api/actors/1/move", json={"direction": "east"})
        snapshot_response = client.get("/api/scenes/1/snapshot")

        assert move_response.status_code == 200
        assert move_response.json()["success"] is True
        assert snapshot_response.json()["actors"][0]["tile_x"] == 1
        assert snapshot_response.json()["actors"][0]["tile_y"] == 0

        connection = sqlite3.connect(str(database))
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT current_coordinate_x, current_coordinate_y "
                "FROM game_player_statuses WHERE player_id = 1"
            ).fetchone()
            assert row is not None
            assert row["current_coordinate_x"] == 1
            assert row["current_coordinate_y"] == 0
        finally:
            connection.close()
    finally:
        runtime.close()


def test_sqlite_web_runtime_websocket_stream_sees_committed_move_event(tmp_path: Path):
    database = tmp_path / "runtime.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
        )
    )
    try:
        client = TestClient(runtime.app)
        client.post("/api/actors/1/move", json={"direction": "east"})

        with client.websocket_connect(
            "/api/scenes/spot-1/stream?last_seen_scene_version=0"
        ) as websocket:
            response = websocket.receive_json()
            assert response["type"] == "scene_events"
            assert response["events"][0]["event_type"] == "actor_moved"
            assert response["events"][0]["payload"]["to_tile_x"] == 1
    finally:
        runtime.close()
