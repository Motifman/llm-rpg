"""Integration-style tests for SQLite-backed web runtime composition."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from ai_rpg_world.presentation.web.demo_seed import (
    seed_demo_world_database,
)
from ai_rpg_world.presentation.web.runtime import (
    SqliteWebAppConfig,
    create_sqlite_web_runtime,
)


def _move_until_success(client: TestClient, direction: str, *, retries: int = 20) -> None:
    response = None
    for _ in range(retries):
        response = client.post(
            "/api/actors/1/move",
            json={"direction": direction},
        )
        if response.status_code == 200:
            return
        time.sleep(0.06)
    assert response is not None
    assert response.status_code == 200


def _move_with_response(
    client: TestClient,
    direction: str,
    *,
    retries: int = 20,
):
    response = None
    for _ in range(retries):
        response = client.post(
            "/api/actors/1/move",
            json={"direction": direction},
        )
        if response.status_code == 200:
            return response
        time.sleep(0.06)
    assert response is not None
    assert response.status_code == 200
    return response


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
        assert payload["monsters"][0]["display_name"] == "Slime"
        assert payload["objects"][0]["display_name"] == "宝箱"
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
        assert snapshot_response.json()["actors"][0]["tile_x"] == 3
        assert snapshot_response.json()["actors"][0]["tile_y"] == 13

        connection = sqlite3.connect(str(database))
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT current_coordinate_x, current_coordinate_y "
                "FROM game_player_statuses WHERE player_id = 1"
            ).fetchone()
            assert row is not None
            assert row["current_coordinate_x"] == 3
            assert row["current_coordinate_y"] == 13
        finally:
            connection.close()
    finally:
        runtime.close()


def test_sqlite_web_runtime_advances_ticks_and_unblocks_busy_manual_movement(
    tmp_path: Path,
):
    database = tmp_path / "runtime-loop.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
            tick_interval_ms=200,
        )
    )
    try:
        with TestClient(runtime.app) as client:
            first_move = client.post("/api/actors/1/move", json={"direction": "east"})
            blocked_move = client.post("/api/actors/1/move", json={"direction": "east"})
            second_move = None
            for _ in range(10):
                time.sleep(0.08)
                second_move = client.post("/api/actors/1/move", json={"direction": "east"})
                if second_move.status_code == 200:
                    break
            snapshot_response = client.get("/api/scenes/1/snapshot")

        assert first_move.status_code == 200
        assert blocked_move.status_code == 400
        assert "現在行動中" in blocked_move.json()["detail"]
        assert second_move is not None
        assert second_move.status_code == 200
        assert snapshot_response.json()["actors"][0]["tile_x"] == 4
        assert snapshot_response.json()["simulation"]["current_tick"] >= 101
    finally:
        runtime.close()


def test_sqlite_web_runtime_gateway_transition_moves_actor_between_spots(
    tmp_path: Path,
):
    database = tmp_path / "runtime-gateway.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
            tick_interval_ms=20,
        )
    )
    try:
        with TestClient(runtime.app) as client:
            for direction in ("east",) * 6 + ("north",) * 11:
                _move_until_success(client, direction)
                time.sleep(0.06)

            gateway_response = _move_with_response(client, "north")
            source_snapshot = client.get("/api/scenes/1/snapshot").json()
            target_snapshot = client.get("/api/scenes/2/snapshot").json()

        assert gateway_response.status_code == 200
        payload = gateway_response.json()
        assert payload["to_spot_id"] == 2
        assert payload["to_coordinate"] == {"x": 6, "y": 9, "z": 0}
        assert source_snapshot["actors"] == []
        assert target_snapshot["actors"][0]["tile_x"] == 6
        assert target_snapshot["actors"][0]["tile_y"] == 9

        connection = sqlite3.connect(str(database))
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT current_spot_id, current_coordinate_x, current_coordinate_y "
                "FROM game_player_statuses WHERE player_id = 1"
            ).fetchone()
            assert row is not None
            assert row["current_spot_id"] == 2
            assert row["current_coordinate_x"] == 6
            assert row["current_coordinate_y"] == 9
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
            assert response["events"][0]["payload"]["to_tile_x"] == 3
    finally:
        runtime.close()


def test_sqlite_web_runtime_snapshot_current_tick_advances_without_scene_version_growth(
    tmp_path: Path,
):
    database = tmp_path / "runtime-stream.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
            tick_interval_ms=20,
        )
    )
    try:
        with TestClient(runtime.app) as client:
            before = client.get("/api/scenes/1/snapshot").json()
            time.sleep(0.06)
            after = client.get("/api/scenes/1/snapshot").json()
        assert after["simulation"]["current_tick"] > before["simulation"]["current_tick"]
        assert after["scene_version"] == before["scene_version"]
    finally:
        runtime.close()


def test_sqlite_web_runtime_demo_monster_moves_and_updates_snapshot(tmp_path: Path):
    database = tmp_path / "runtime-monster.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
            tick_interval_ms=20,
        )
    )
    try:
        with TestClient(runtime.app) as client:
            before = client.get("/api/scenes/1/snapshot").json()
            after = before
            for _ in range(24):
                time.sleep(0.08)
                after = client.get("/api/scenes/1/snapshot").json()
                if (
                    before["monsters"][0]["tile_x"],
                    before["monsters"][0]["tile_y"],
                ) != (
                    after["monsters"][0]["tile_x"],
                    after["monsters"][0]["tile_y"],
                ):
                    break

        assert before["monsters"][0]["display_name"] == "Slime"
        assert after["monsters"][0]["display_name"] == "Slime"
        assert (before["monsters"][0]["tile_x"], before["monsters"][0]["tile_y"]) != (
            after["monsters"][0]["tile_x"],
            after["monsters"][0]["tile_y"],
        )
        assert after["scene_version"] > before["scene_version"]
    finally:
        runtime.close()


def test_sqlite_web_runtime_interact_endpoint_updates_chest_state_and_logs(
    tmp_path: Path,
):
    database = tmp_path / "runtime-interact.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
        )
    )
    try:
        with TestClient(runtime.app) as client:
            for direction in ("east",) * 2 + ("north",) * 7:
                _move_until_success(client, direction)
                time.sleep(0.06)
            snapshot = client.get("/api/scenes/1/snapshot").json()
            for _ in range(20):
                actor = snapshot["actors"][0]
                if (
                    actor["tile_x"] == 4
                    and actor["tile_y"] == 6
                    and actor["facing"] == "north"
                    and actor["state"] == "idle"
                ):
                    break
                time.sleep(0.06)
                snapshot = client.get("/api/scenes/1/snapshot").json()
            response = None
            for _ in range(20):
                response = client.post(
                    "/api/actors/1/interact",
                    json={"target_object_id": 10001},
                )
                if response.status_code == 200:
                    break
                time.sleep(0.06)
            snapshot = client.get("/api/scenes/1/snapshot").json()

        assert response is not None
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["object_state"]["is_open"] is True
        assert snapshot["objects"][0]["interaction_data"]["is_open"] is True
        assert any("宝箱を開けました" in entry["message"] for entry in snapshot["ui_logs"])
    finally:
        runtime.close()


def test_sqlite_web_runtime_interact_auto_turns_actor_toward_target(
    tmp_path: Path,
):
    database = tmp_path / "runtime-interact-facing.db"
    seed_demo_world_database(database)

    runtime = create_sqlite_web_runtime(
        SqliteWebAppConfig(
            database_path=database,
            manual_player_ids=(1,),
            initial_tick=100,
        )
    )
    try:
        with TestClient(runtime.app) as client:
            path = ("east",) * 2 + ("north",) * 7 + ("west", "east")
            for direction in path:
                _move_until_success(client, direction)
                time.sleep(0.06)

            for _ in range(20):
                snapshot = client.get("/api/scenes/1/snapshot").json()
                actor = snapshot["actors"][0]
                if (
                    actor["tile_x"] == 4
                    and actor["tile_y"] == 6
                    and actor["facing"] == "east"
                    and actor["state"] == "idle"
                ):
                    break
                time.sleep(0.06)

            response = client.post(
                "/api/actors/1/interact",
                json={"target_object_id": 10001},
            )
            snapshot = client.get("/api/scenes/1/snapshot").json()

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert snapshot["objects"][0]["interaction_data"]["is_open"] is True
        assert snapshot["actors"][0]["facing"] == "north"
    finally:
        runtime.close()
