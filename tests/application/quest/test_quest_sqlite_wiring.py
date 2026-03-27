"""Quest SQLite wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.quest.quest_sqlite_wiring import (
    attach_quest_sqlite_repositories,
    bootstrap_quest_schema,
)


def test_quest_sqlite_wiring_bootstrap_and_attach() -> None:
    conn = sqlite3.connect(":memory:")
    bootstrap_quest_schema(conn)
    repos = attach_quest_sqlite_repositories(conn)

    assert repos.quests is not None
