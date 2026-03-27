"""Social SQLite wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.social.social_sqlite_wiring import (
    attach_social_sqlite_repositories,
    bootstrap_social_schema,
)


def test_social_sqlite_wiring_bootstrap_and_attach() -> None:
    conn = sqlite3.connect(":memory:")
    bootstrap_social_schema(conn)
    repos = attach_social_sqlite_repositories(conn)

    assert repos.users is not None
    assert repos.posts is not None
    assert repos.replies is not None
    assert repos.notifications is not None
