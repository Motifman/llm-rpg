"""SQLite guild bank repository tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.domain.guild.aggregate.guild_bank_aggregate import GuildBankAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.sqlite_guild_bank_repository import (
    SqliteGuildBankRepository,
)


def test_guild_bank_repository_roundtrip() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteGuildBankRepository.for_standalone_connection(conn)

    bank = GuildBankAggregate.create_for_guild(GuildId(1))
    bank.deposit_gold(150, PlayerId(10))
    repo.save(bank)

    loaded = repo.find_by_id(GuildId(1))
    assert loaded is not None
    assert loaded.gold.value == 150
