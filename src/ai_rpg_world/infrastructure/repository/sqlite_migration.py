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
    savepoint_name = f"migration_{namespace.replace('-', '_')}"
    if started_without_transaction:
        connection.execute("BEGIN")
    else:
        connection.execute(f"SAVEPOINT {savepoint_name}")

    try:
        ensure_migration_table(connection)
        applied_version = get_applied_version(connection, namespace)
        ordered = sorted(migrations, key=lambda item: item.version)

        latest_version = applied_version
        for migration in ordered:
            if migration.version <= applied_version:
                latest_version = max(latest_version, migration.version)
                continue
            migration.apply(connection)
            latest_version = migration.version
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

        if started_without_transaction:
            connection.commit()
        else:
            connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        return latest_version
    except Exception:
        if started_without_transaction:
            if connection.in_transaction:
                connection.rollback()
        else:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        raise


__all__ = [
    "SqliteMigration",
    "apply_migrations",
    "ensure_migration_table",
    "get_applied_version",
]
