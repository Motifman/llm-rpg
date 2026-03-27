"""SQLite guild repository tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_guild_repository import (
    SqliteGuildRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _guild(guild_id: int, *, creator_id: int = 100) -> GuildAggregate:
    return GuildAggregate.create_guild(
        guild_id=GuildId(guild_id),
        spot_id=SpotId(10),
        location_area_id=LocationAreaId(20),
        name="Hunters",
        description="Guild for tests",
        creator_player_id=PlayerId(creator_id),
    )


def test_guild_repository_roundtrip_and_member_lookup_index_sync() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteGuildRepository.for_standalone_connection(conn)

    guild = _guild(1)
    guild.add_member(PlayerId(100), PlayerId(200))
    repo.save(guild)

    loaded = repo.find_by_id(GuildId(1))
    assert loaded is not None
    assert loaded.guild_id == GuildId(1)

    by_location = repo.find_by_spot_and_location(SpotId(10), LocationAreaId(20))
    assert by_location is not None
    assert by_location.guild_id == GuildId(1)

    member_guilds = repo.find_guilds_by_player_id(PlayerId(200))
    assert [guild.guild_id for guild in member_guilds] == [GuildId(1)]


def test_guild_repository_delete_cleans_member_index() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteGuildRepository.for_standalone_connection(conn)

    guild = _guild(1)
    guild.add_member(PlayerId(100), PlayerId(200))
    repo.save(guild)

    assert repo.delete(GuildId(1)) is True
    assert repo.find_guilds_by_player_id(PlayerId(200)) == []


def test_guild_repository_generates_ids_inside_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    uow = SqliteUnitOfWork(connection=conn)

    with uow:
        repo = SqliteGuildRepository.for_shared_unit_of_work(uow.connection)
        assert repo.generate_guild_id() == GuildId(1)
        assert repo.generate_guild_id() == GuildId(2)
