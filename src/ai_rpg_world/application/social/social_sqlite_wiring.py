"""SQLite repository bundle for SNS/social domain on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import (
    SqlitePostRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import (
    SqliteReplyRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import (
    SqliteSnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import (
    SqliteSnsUserRepository,
)


@dataclass(frozen=True)
class SocialSqliteRepositories:
    users: SqliteSnsUserRepository
    posts: SqlitePostRepository
    replies: SqliteReplyRepository
    notifications: SqliteSnsNotificationRepository


def bootstrap_social_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for social state."""
    init_game_db_schema(connection)


def attach_social_sqlite_repositories(
    connection: sqlite3.Connection,
    *,
    event_sink: object | None = None,
) -> SocialSqliteRepositories:
    """Attach social SQLite repositories to a shared connection."""
    return SocialSqliteRepositories(
        users=SqliteSnsUserRepository.for_shared_unit_of_work(connection, event_sink=event_sink),
        posts=SqlitePostRepository.for_shared_unit_of_work(connection, event_sink=event_sink),
        replies=SqliteReplyRepository.for_shared_unit_of_work(connection, event_sink=event_sink),
        notifications=SqliteSnsNotificationRepository.for_shared_unit_of_work(
            connection, event_sink=event_sink
        ),
    )


__all__ = [
    "SocialSqliteRepositories",
    "attach_social_sqlite_repositories",
    "bootstrap_social_schema",
]
