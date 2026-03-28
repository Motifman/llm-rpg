"""Integration-style tests for SQLite-backed web runtime composition."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
    StatGrowthFactor,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
    PhysicalMapAggregate,
)
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWorkFactory,
)
from ai_rpg_world.presentation.web.runtime import (
    SqliteWebAppConfig,
    create_sqlite_web_runtime,
)


def _seed_world(database: Path) -> None:
    factory = SqliteUnitOfWorkFactory(database)
    with factory.create() as uow:
        world_state = attach_world_state_sqlite_repositories(
            uow.connection,
            event_sink=uow,
        )
        world_state.world_structure.spots.save(Spot(SpotId(1), "Starter Town", ""))

        exp_table = ExpTable(100, 1.5)
        navigation_state = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        world_state.player_state.player_profiles.save(
            PlayerProfileAggregate.create(
                player_id=PlayerId(1),
                name=PlayerName("Hero"),
                role=Role.CITIZEN,
            )
        )
        world_state.player_state.player_statuses.save(
            PlayerStatusAggregate(
                player_id=PlayerId(1),
                base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
                stat_growth_factor=StatGrowthFactor(
                    1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01
                ),
                exp_table=exp_table,
                growth=Growth(1, 0, exp_table),
                gold=Gold(100),
                hp=Hp.create(100, 100),
                mp=Mp.create(50, 50),
                stamina=Stamina.create(100, 100),
                navigation_state=navigation_state,
            )
        )

        tiles = {
            Coordinate(x, y, 0): Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(3)
            for y in range(3)
        }
        physical_map = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[
                WorldObject(
                    object_id=WorldObjectId.create(1),
                    coordinate=Coordinate(0, 0, 0),
                    object_type=ObjectTypeEnum.PLAYER,
                    component=ActorComponent(
                        direction=DirectionEnum.EAST,
                        player_id=PlayerId(1),
                    ),
                )
            ],
        )
        world_state.world_runtime.physical_maps.save(physical_map)


def test_create_sqlite_web_runtime_bootstraps_projection_from_sqlite(tmp_path: Path):
    database = tmp_path / "runtime.db"
    _seed_world(database)

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

        assert response.status_code == 200
        payload = response.json()
        assert payload["spot_name"] == "Starter Town"
        assert payload["actors"][0]["display_name"] == "Hero"
        assert payload["actors"][0]["is_manual_controlled"] is True
    finally:
        runtime.close()


def test_sqlite_web_runtime_move_endpoint_updates_projection_and_database(tmp_path: Path):
    database = tmp_path / "runtime.db"
    _seed_world(database)

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
    _seed_world(database)

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
