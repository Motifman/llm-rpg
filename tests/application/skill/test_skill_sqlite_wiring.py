"""Skill SQLite wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.skill.skill_sqlite_wiring import (
    attach_skill_sqlite_repositories,
    bootstrap_skill_schema,
)


def test_skill_sqlite_wiring_bootstrap_and_attach() -> None:
    conn = sqlite3.connect(":memory:")
    bootstrap_skill_schema(conn)
    repos = attach_skill_sqlite_repositories(conn)

    assert repos.runtime.loadouts is not None
    assert repos.runtime.deck_progresses is not None
    assert repos.master.specs is not None
    assert repos.master.spec_writer is not None
