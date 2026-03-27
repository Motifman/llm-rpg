"""SQLite HitBoxRepository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.sqlite_hit_box_repository import (
    SqliteHitBoxRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _hit_box(
    hit_box_id: int,
    spot_id: int,
    owner_id: int,
    x: int = 0,
    y: int = 0,
) -> HitBoxAggregate:
    return HitBoxAggregate.create(
        hit_box_id=HitBoxId.create(hit_box_id),
        spot_id=SpotId(spot_id),
        owner_id=WorldObjectId.create(owner_id),
        shape=HitBoxShape.single_cell(),
        initial_coordinate=Coordinate(x, y, 0),
        start_tick=WorldTick(0),
        duration=5,
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteHitBoxRepository:
    def test_shared_repository_requires_active_transaction_for_save(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteHitBoxRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(_hit_box(1, 1, 100))

    def test_save_and_find_roundtrip(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteHitBoxRepository.for_standalone_connection(sqlite_conn)
        hit_box = _hit_box(1, 7, 1000, x=1, y=2)
        hit_box.record_hit(WorldObjectId.create(2000))
        repo.save(hit_box)

        loaded = repo.find_by_id(HitBoxId(1))
        assert loaded is not None
        assert loaded.hit_box_id == HitBoxId(1)
        assert loaded.spot_id == SpotId(7)
        assert loaded.current_coordinate == Coordinate(1, 2, 0)
        assert loaded.has_hit(WorldObjectId.create(2000))

    def test_find_active_by_spot_id_excludes_inactive(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteHitBoxRepository.for_standalone_connection(sqlite_conn)
        active = _hit_box(1, 1, 100)
        inactive = _hit_box(2, 1, 101, x=1)
        other_spot = _hit_box(3, 2, 102, x=2)
        inactive.deactivate()
        repo.save_all([active, inactive, other_spot])

        all_on_spot = repo.find_by_spot_id(SpotId(1))
        active_on_spot = repo.find_active_by_spot_id(SpotId(1))

        assert {hb.hit_box_id for hb in all_on_spot} == {HitBoxId(1), HitBoxId(2)}
        assert [hb.hit_box_id for hb in active_on_spot] == [HitBoxId(1)]

    def test_batch_generate_ids_uses_transactional_sequence(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            repo = SqliteHitBoxRepository.for_shared_unit_of_work(uow.connection)
            generated = repo.batch_generate_ids(3)

        assert [hit_box_id.value for hit_box_id in generated] == [1, 2, 3]

    def test_hit_box_id_sequence_rolls_back(self, sqlite_conn: sqlite3.Connection) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with pytest.raises(RuntimeError, match="abort"):
            with uow:
                repo = SqliteHitBoxRepository.for_shared_unit_of_work(uow.connection)
                generated = repo.generate_id()
                assert generated.value == 1
                raise RuntimeError("abort")

        with uow:
            repo = SqliteHitBoxRepository.for_shared_unit_of_work(uow.connection)
            generated2 = repo.generate_id()
        assert generated2.value == 1
