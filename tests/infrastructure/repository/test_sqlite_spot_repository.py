"""SQLite SpotRepository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_spot_repository import (
    SqliteSpotRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteSpotRepository:
    def test_shared_repository_requires_active_transaction_for_save(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteSpotRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(Spot(SpotId(1), "Town", "desc", SpotCategoryEnum.TOWN))

    def test_save_and_find_by_id_roundtrip(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteSpotRepository.for_standalone_connection(sqlite_conn)
        repo.save(Spot(SpotId(1), "Town", "A starting town", SpotCategoryEnum.TOWN))

        loaded = repo.find_by_id(SpotId(1))
        assert loaded is not None
        assert loaded.name == "Town"
        assert loaded.description == "A starting town"
        assert loaded.category == SpotCategoryEnum.TOWN

    def test_find_by_name_uses_trimmed_exact_match(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteSpotRepository.for_standalone_connection(sqlite_conn)
        repo.save(Spot(SpotId(1), "北の森", "冒険の森", SpotCategoryEnum.FIELD))

        found = repo.find_by_name("  北の森  ")

        assert found is not None
        assert found.spot_id == SpotId(1)

    def test_find_by_name_returns_none_for_blank_or_missing(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteSpotRepository.for_standalone_connection(sqlite_conn)
        repo.save(Spot(SpotId(1), "Town", "", SpotCategoryEnum.TOWN))

        assert repo.find_by_name("   ") is None
        assert repo.find_by_name("Missing") is None

    def test_find_all_and_delete(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteSpotRepository.for_standalone_connection(sqlite_conn)
        repo.save(Spot(SpotId(1), "A", "", SpotCategoryEnum.OTHER))
        repo.save(Spot(SpotId(2), "B", "", SpotCategoryEnum.SHOP, parent_id=SpotId(1)))

        all_spots = repo.find_all()
        assert [spot.spot_id for spot in all_spots] == [SpotId(1), SpotId(2)]
        assert all_spots[1].parent_id == SpotId(1)
        assert repo.delete(SpotId(1)) is True
        assert repo.find_by_id(SpotId(1)) is None

    def test_shared_uow_write_is_visible_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            repo = SqliteSpotRepository.for_shared_unit_of_work(uow.connection)
            repo.save(Spot(SpotId(1), "Inn", "sleep", SpotCategoryEnum.INN))
            loaded = repo.find_by_id(SpotId(1))
            assert loaded is not None
            assert loaded.name == "Inn"
