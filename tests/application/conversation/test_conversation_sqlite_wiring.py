"""Conversation SQLite wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.conversation.conversation_sqlite_wiring import (
    attach_conversation_sqlite_repositories,
    bootstrap_conversation_schema,
)


def test_conversation_sqlite_wiring_bootstrap_and_attach() -> None:
    conn = sqlite3.connect(":memory:")
    bootstrap_conversation_schema(conn)
    repos = attach_conversation_sqlite_repositories(conn)

    assert repos.dialogue_trees is not None
    assert repos.dialogue_tree_writer is not None
