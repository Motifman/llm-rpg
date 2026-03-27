"""SQLite PhysicalMapRepository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.sqlite_physical_map_repository import (
    SqlitePhysicalMapRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _tile_at(x: int, y: int) -> Tile:
    return Tile(Coordinate(x, y, 0), TerrainType.grass())


def _player_object(player_id: int, x: int = 0, y: int = 0) -> WorldObject:
    return WorldObject(
        object_id=WorldObjectId(player_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.PLAYER,
        component=ActorComponent(
            direction=DirectionEnum.SOUTH,
            player_id=PlayerId(player_id),
        ),
    )


def _physical_map(spot_id: int, objects: list[WorldObject]) -> PhysicalMapAggregate:
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles={
            Coordinate(0, 0, 0): _tile_at(0, 0),
            Coordinate(1, 0, 0): _tile_at(1, 0),
        },
        objects=objects,
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqlitePhysicalMapRepository:
    def test_shared_repository_requires_active_transaction_for_save(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqlitePhysicalMapRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(_physical_map(1, [_player_object(1)]))

    def test_save_and_find_roundtrip(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqlitePhysicalMapRepository.for_standalone_connection(sqlite_conn)
        original = _physical_map(10, [_player_object(1)])
        repo.save(original)

        loaded = repo.find_by_spot_id(SpotId(10))
        assert loaded is not None
        assert loaded.spot_id == SpotId(10)
        loaded_player = loaded.get_object(WorldObjectId(1))
        assert loaded_player.coordinate == Coordinate(0, 0, 0)
        assert loaded_player.player_id == PlayerId(1)

    def test_find_spot_id_by_object_id_updates_on_replace(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqlitePhysicalMapRepository.for_standalone_connection(sqlite_conn)
        repo.save(_physical_map(5, [_player_object(1)]))
        assert repo.find_spot_id_by_object_id(WorldObjectId(1)) == SpotId(5)

        repo.save(_physical_map(5, [_player_object(2)]))
        assert repo.find_spot_id_by_object_id(WorldObjectId(1)) is None
        assert repo.find_spot_id_by_object_id(WorldObjectId(2)) == SpotId(5)

    def test_delete_removes_snapshot_and_index(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqlitePhysicalMapRepository.for_standalone_connection(sqlite_conn)
        repo.save(_physical_map(7, [_player_object(3)]))
        assert repo.delete(SpotId(7)) is True
        assert repo.find_by_spot_id(SpotId(7)) is None
        assert repo.find_spot_id_by_object_id(WorldObjectId(3)) is None
        assert repo.find_connected_spot_ids(SpotId(7)) == []

    def test_connected_spot_index_updates_on_save_and_replace(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.area import PointArea
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId

        repo = SqlitePhysicalMapRepository.for_standalone_connection(sqlite_conn)
        original = PhysicalMapAggregate.create(
            SpotId(10),
            [_tile_at(0, 0), _tile_at(1, 0)],
            gateways=[
                Gateway(
                    gateway_id=GatewayId(1),
                    name="to-2",
                    area=PointArea(Coordinate(0, 0, 0)),
                    target_spot_id=SpotId(2),
                    landing_coordinate=Coordinate(0, 0, 0),
                ),
                Gateway(
                    gateway_id=GatewayId(2),
                    name="to-3",
                    area=PointArea(Coordinate(1, 0, 0)),
                    target_spot_id=SpotId(3),
                    landing_coordinate=Coordinate(0, 0, 0),
                ),
            ],
        )
        repo.save(original)
        assert repo.find_connected_spot_ids(SpotId(10)) == [SpotId(2), SpotId(3)]

        replaced = PhysicalMapAggregate.create(
            SpotId(10),
            [_tile_at(0, 0), _tile_at(1, 0)],
            gateways=[],
        )
        repo.save(replaced)
        assert repo.find_connected_spot_ids(SpotId(10)) == []

    def test_gateway_index_backfills_existing_maps_on_init(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.area import PointArea
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            init_game_write_schema,
        )
        from ai_rpg_world.infrastructure.repository.sqlite_world_state_codec import (
            physical_map_to_blob,
        )

        init_game_write_schema(sqlite_conn)
        physical_map = PhysicalMapAggregate.create(
            SpotId(20),
            [_tile_at(0, 0), _tile_at(1, 0)],
            gateways=[
                Gateway(
                    gateway_id=GatewayId(1),
                    name="to-4",
                    area=PointArea(Coordinate(0, 0, 0)),
                    target_spot_id=SpotId(4),
                    landing_coordinate=Coordinate(0, 0, 0),
                )
            ],
        )
        sqlite_conn.execute(
            "INSERT INTO game_physical_maps (spot_id, aggregate_blob) VALUES (?, ?)",
            (20, physical_map_to_blob(physical_map)),
        )
        sqlite_conn.commit()

        repo = SqlitePhysicalMapRepository.for_standalone_connection(sqlite_conn)
        assert repo.find_connected_spot_ids(SpotId(20)) == [SpotId(4)]

    def test_world_object_id_sequence_starts_above_player_range(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            repo = SqlitePhysicalMapRepository.for_shared_unit_of_work(uow.connection)
            wid1 = repo.generate_world_object_id()
            wid2 = repo.generate_world_object_id()

        assert wid1.value == 100000
        assert wid2.value == 100001

    def test_world_object_id_sequence_rolls_back(self, sqlite_conn: sqlite3.Connection) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with pytest.raises(RuntimeError, match="abort"):
            with uow:
                repo = SqlitePhysicalMapRepository.for_shared_unit_of_work(uow.connection)
                wid = repo.generate_world_object_id()
                assert wid.value == 100000
                raise RuntimeError("abort")

        with uow:
            repo = SqlitePhysicalMapRepository.for_shared_unit_of_work(uow.connection)
            wid2 = repo.generate_world_object_id()
        assert wid2.value == 100000
