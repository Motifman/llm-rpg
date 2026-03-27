"""SQLite LocationEstablishmentRepository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.enum.world_enum import EstablishmentType
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_location_establishment_repository import (
    SqliteLocationEstablishmentRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteLocationEstablishmentRepository:
    def test_shared_repository_requires_active_transaction_for_save(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteLocationEstablishmentRepository.for_shared_unit_of_work(sqlite_conn)
        slot = LocationEstablishmentAggregate.create(SpotId(1), LocationAreaId(1))
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(slot)

    def test_save_and_find_by_id(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteLocationEstablishmentRepository.for_standalone_connection(sqlite_conn)
        slot = LocationEstablishmentAggregate.create(SpotId(1), LocationAreaId(1))
        repo.save(slot)

        found = repo.find_by_id(LocationSlotId(SpotId(1), LocationAreaId(1)))
        assert found is not None
        assert found.spot_id == SpotId(1)
        assert found.location_area_id == LocationAreaId(1)
        assert found.is_occupied() is False

    def test_find_by_spot_and_location(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteLocationEstablishmentRepository.for_standalone_connection(sqlite_conn)
        slot = LocationEstablishmentAggregate.create(SpotId(1), LocationAreaId(2))
        slot.claim(EstablishmentType.SHOP, 10)
        repo.save(slot)

        found = repo.find_by_spot_and_location(SpotId(1), LocationAreaId(2))
        assert found is not None
        assert found.establishment_type == EstablishmentType.SHOP
        assert found.establishment_id == 10

    def test_release_persists_empty_slot_instead_of_deleting(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteLocationEstablishmentRepository.for_standalone_connection(sqlite_conn)
        slot = LocationEstablishmentAggregate.create(SpotId(2), LocationAreaId(3))
        slot.claim(EstablishmentType.GUILD, 55)
        repo.save(slot)
        slot.release()
        repo.save(slot)

        found = repo.find_by_spot_and_location(SpotId(2), LocationAreaId(3))
        assert found is not None
        assert found.is_occupied() is False
        assert found.establishment_type is None
        assert found.establishment_id is None

    def test_find_by_ids_and_delete(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteLocationEstablishmentRepository.for_standalone_connection(sqlite_conn)
        slot1 = LocationEstablishmentAggregate.create(SpotId(1), LocationAreaId(1))
        slot2 = LocationEstablishmentAggregate.create(SpotId(2), LocationAreaId(2))
        repo.save(slot1)
        repo.save(slot2)

        found = repo.find_by_ids(
            [
                LocationSlotId(SpotId(1), LocationAreaId(1)),
                LocationSlotId(SpotId(9), LocationAreaId(9)),
                LocationSlotId(SpotId(2), LocationAreaId(2)),
            ]
        )
        assert [slot.id for slot in found] == [
            LocationSlotId(SpotId(1), LocationAreaId(1)),
            LocationSlotId(SpotId(2), LocationAreaId(2)),
        ]
        assert repo.delete(LocationSlotId(SpotId(1), LocationAreaId(1))) is True
        assert repo.find_by_spot_and_location(SpotId(1), LocationAreaId(1)) is None

    def test_shared_uow_write_is_visible_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            repo = SqliteLocationEstablishmentRepository.for_shared_unit_of_work(
                uow.connection
            )
            slot = LocationEstablishmentAggregate.create(SpotId(1), LocationAreaId(4))
            slot.claim(EstablishmentType.SHOP, 99)
            repo.save(slot)
            loaded = repo.find_by_spot_and_location(SpotId(1), LocationAreaId(4))
            assert loaded is not None
            assert loaded.establishment_id == 99
