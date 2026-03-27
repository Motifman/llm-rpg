"""Guild SQLite wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.guild.guild_sqlite_wiring import (
    attach_guild_sqlite_repositories,
    bootstrap_guild_schema,
)


def test_guild_sqlite_wiring_bootstrap_and_attach() -> None:
    conn = sqlite3.connect(":memory:")
    bootstrap_guild_schema(conn)
    repos = attach_guild_sqlite_repositories(conn)

    assert repos.guilds is not None
    assert repos.guild_banks is not None
