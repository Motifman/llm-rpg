"""Lightweight SQLite migration helpers for repository-owned schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Callable, Iterable


@dataclass(frozen=True)
class SqliteMigration:
    """Single ordered migration for a logical schema namespace."""

    version: int
    apply: Callable[[sqlite3.Connection], None]


def ensure_migration_table(connection: sqlite3.Connection) -> None:
    """Create the migration bookkeeping table if it does not exist."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            namespace TEXT PRIMARY KEY NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def get_applied_version(connection: sqlite3.Connection, namespace: str) -> int:
    """Return the applied version for a namespace, or 0 when uninitialized."""
    ensure_migration_table(connection)
    cur = connection.execute(
        "SELECT version FROM schema_migrations WHERE namespace = ?",
        (namespace,),
    )
    row = cur.fetchone()
    if row is None:
        return 0
    return int(row[0])


def apply_migrations(
    connection: sqlite3.Connection,
    *,
    namespace: str,
    migrations: Iterable[SqliteMigration],
) -> int:
    """Apply unapplied migrations in order and return the latest version."""
    started_without_transaction = not connection.in_transaction
    ensure_migration_table(connection)
    applied_version = get_applied_version(connection, namespace)
    ordered = sorted(migrations, key=lambda item: item.version)

    latest_version = applied_version
    changed = False
    for migration in ordered:
        if migration.version <= applied_version:
            latest_version = max(latest_version, migration.version)
            continue
        migration.apply(connection)
        latest_version = migration.version
        changed = True
        connection.execute(
            """
            INSERT INTO schema_migrations (namespace, version, applied_at)
            VALUES (?, ?, ?)
            ON CONFLICT(namespace) DO UPDATE SET
                version = excluded.version,
                applied_at = excluded.applied_at
            """,
            (
                namespace,
                latest_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    # Standalone sqlite3 connections keep an implicit transaction open after DDL/DML.
    # Commit only when schema initialization was invoked outside an existing UoW tx.
    if changed and started_without_transaction and connection.in_transaction:
        connection.commit()

    return latest_version


__all__ = [
    "SqliteMigration",
    "apply_migrations",
    "ensure_migration_table",
    "get_applied_version",
]
