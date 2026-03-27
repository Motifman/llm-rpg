"""SQLite transition policy repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import (
    RequireRelation,
    RequireToll,
    block_if_weather,
)
from ai_rpg_world.infrastructure.repository.sqlite_transition_policy_repository import (
    SqliteTransitionPolicyRepository,
    SqliteTransitionPolicyWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteTransitionPolicyRepository:
    def test_get_conditions_empty_when_nothing_set(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteTransitionPolicyRepository.for_standalone_connection(sqlite_conn)
        assert repo.get_conditions(SpotId(1), SpotId(2)) == []

    def test_set_and_get_conditions_roundtrip(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteTransitionPolicyRepository.for_standalone_connection(sqlite_conn)
        writer = SqliteTransitionPolicyWriter.for_standalone_connection(sqlite_conn)
        writer.replace_conditions(
            SpotId(1),
            SpotId(2),
            [
                RequireToll(amount_gold=10),
                block_if_weather([WeatherTypeEnum.BLIZZARD]),
                RequireRelation(relation_type="guild_member"),
            ],
        )

        result = repo.get_conditions(SpotId(1), SpotId(2))
        assert len(result) == 3
        assert isinstance(result[0], RequireToll)
        assert result[0].amount_gold == 10
        assert WeatherTypeEnum.BLIZZARD in result[1].blocked_weather_types
        assert isinstance(result[2], RequireRelation)
        assert result[2].relation_type == "guild_member"

    def test_get_conditions_returns_fresh_list(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteTransitionPolicyRepository.for_standalone_connection(sqlite_conn)
        writer = SqliteTransitionPolicyWriter.for_standalone_connection(sqlite_conn)
        writer.replace_conditions(SpotId(1), SpotId(2), [RequireToll(amount_gold=5)])
        result = repo.get_conditions(SpotId(1), SpotId(2))
        result.append(RequireToll(amount_gold=99))
        assert len(repo.get_conditions(SpotId(1), SpotId(2))) == 1

    def test_shared_writer_requires_active_transaction_for_replace(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteTransitionPolicyWriter.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="writer"):
            writer.replace_conditions(SpotId(1), SpotId(2), [RequireToll(amount_gold=5)])

    def test_writer_replace_is_visible_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            repo = SqliteTransitionPolicyRepository.for_shared_unit_of_work(uow.connection)
            writer = SqliteTransitionPolicyWriter.for_shared_unit_of_work(uow.connection)
            writer.replace_conditions(
                SpotId(3),
                SpotId(4),
                [block_if_weather([WeatherTypeEnum.STORM])],
            )
            result = repo.get_conditions(SpotId(3), SpotId(4))
            assert len(result) == 1
            assert WeatherTypeEnum.STORM in result[0].blocked_weather_types
