"""SQLite WeatherZoneRepository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.weather_zone_name import WeatherZoneName
from ai_rpg_world.infrastructure.repository.sqlite_weather_zone_repository import (
    SqliteWeatherZoneRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _zone(zone_id: int, name: str, spots: set[int], weather_type: WeatherTypeEnum) -> WeatherZone:
    return WeatherZone.create(
        zone_id=WeatherZoneId(zone_id),
        name=WeatherZoneName(name),
        spot_ids={SpotId(spot_id) for spot_id in spots},
        current_state=WeatherState(weather_type, 0.5),
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteWeatherZoneRepository:
    def test_shared_repository_requires_active_transaction_for_save(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteWeatherZoneRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(_zone(1, "north", {1}, WeatherTypeEnum.RAIN))

    def test_save_and_find_roundtrip(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteWeatherZoneRepository.for_standalone_connection(sqlite_conn)
        zone = _zone(1, "north", {1, 2}, WeatherTypeEnum.RAIN)
        repo.save(zone)

        loaded = repo.find_by_id(WeatherZoneId(1))
        assert loaded is not None
        assert loaded.zone_id == WeatherZoneId(1)
        assert loaded.name.value == "north"
        assert loaded.current_state.weather_type == WeatherTypeEnum.RAIN
        assert loaded.spot_ids == {SpotId(1), SpotId(2)}

    def test_find_by_spot_id_uses_reverse_index(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteWeatherZoneRepository.for_standalone_connection(sqlite_conn)
        repo.save(_zone(1, "north", {1, 2}, WeatherTypeEnum.RAIN))
        repo.save(_zone(2, "south", {3}, WeatherTypeEnum.FOG))

        found = repo.find_by_spot_id(SpotId(2))
        missing = repo.find_by_spot_id(SpotId(9))

        assert found is not None
        assert found.zone_id == WeatherZoneId(1)
        assert missing is None

    def test_save_updates_spot_membership_index(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteWeatherZoneRepository.for_standalone_connection(sqlite_conn)
        zone = _zone(1, "north", {1, 2}, WeatherTypeEnum.RAIN)
        repo.save(zone)
        updated = _zone(1, "north", {2, 3}, WeatherTypeEnum.STORM)
        repo.save(updated)

        assert repo.find_by_spot_id(SpotId(1)) is None
        found = repo.find_by_spot_id(SpotId(3))
        assert found is not None
        assert found.current_state.weather_type == WeatherTypeEnum.STORM

    def test_delete_removes_zone_and_spot_index(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteWeatherZoneRepository.for_standalone_connection(sqlite_conn)
        repo.save(_zone(1, "north", {1, 2}, WeatherTypeEnum.RAIN))

        assert repo.delete(WeatherZoneId(1)) is True
        assert repo.find_by_id(WeatherZoneId(1)) is None
        assert repo.find_by_spot_id(SpotId(1)) is None

    def test_shared_uow_write_is_visible_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            repo = SqliteWeatherZoneRepository.for_shared_unit_of_work(
                uow.connection, event_sink=uow
            )
            zone = _zone(3, "mist", {7}, WeatherTypeEnum.FOG)
            repo.save(zone)
            loaded = repo.find_by_spot_id(SpotId(7))
            assert loaded is not None
            assert loaded.zone_id == WeatherZoneId(3)
