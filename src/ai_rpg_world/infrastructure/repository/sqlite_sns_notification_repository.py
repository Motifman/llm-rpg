"""SQLite implementation of SNS notification repository."""

from __future__ import annotations

import copy
import sqlite3
from datetime import datetime
from typing import Any, List, Optional

from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.repository.sns_notification_repository import (
    SnsNotificationRepository,
)
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_state_codec import build_notification


class SqliteSnsNotificationRepository(SnsNotificationRepository):
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        _commits_after_write: bool,
        event_sink: Any = None,
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        self._event_sink = event_sink
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteSnsNotificationRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteSnsNotificationRepository":
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def _hydrate(self, row: sqlite3.Row | None) -> Optional[Notification]:
        if row is None:
            return None
        return copy.deepcopy(
            build_notification(
                (
                    int(row["notification_id"]),
                    int(row["user_id"]),
                    str(row["notification_type"]),
                    str(row["title"]),
                    str(row["message"]),
                    int(row["actor_user_id"]),
                    str(row["actor_user_name"]),
                    None if row["related_post_id"] is None else int(row["related_post_id"]),
                    None if row["related_reply_id"] is None else int(row["related_reply_id"]),
                    row["content_type"],
                    row["content_text"],
                    str(row["created_at"]),
                    int(row["is_read"]),
                    row["expires_at"],
                )
            )
        )

    def _current_max_notification_id(self) -> int:
        cur = self._conn.execute(
            "SELECT COALESCE(MAX(notification_id), 0) FROM game_sns_notifications"
        )
        return int(cur.fetchone()[0])

    def generate_notification_id(self) -> NotificationId:
        self._assert_shared_transaction_active()
        notification_id = NotificationId(
            allocate_sequence_value(
                self._conn,
                "sns_notification_id",
                initial_value=self._current_max_notification_id(),
            )
        )
        self._finalize_write()
        return notification_id

    def save(self, notification: Notification) -> Notification:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(notification)
        self._conn.execute(
            """
            INSERT INTO game_sns_notifications (
                notification_id,
                user_id,
                notification_type,
                title,
                message,
                actor_user_id,
                actor_user_name,
                related_post_id,
                related_reply_id,
                content_type,
                content_text,
                created_at,
                is_read,
                expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(notification_id) DO UPDATE SET
                user_id = excluded.user_id,
                notification_type = excluded.notification_type,
                title = excluded.title,
                message = excluded.message,
                actor_user_id = excluded.actor_user_id,
                actor_user_name = excluded.actor_user_name,
                related_post_id = excluded.related_post_id,
                related_reply_id = excluded.related_reply_id,
                content_type = excluded.content_type,
                content_text = excluded.content_text,
                created_at = excluded.created_at,
                is_read = excluded.is_read,
                expires_at = excluded.expires_at
            """,
            (
                int(notification.notification_id),
                int(notification.user_id),
                notification.notification_type.value,
                notification.content.title,
                notification.content.message,
                int(notification.content.actor_user_id),
                notification.content.actor_user_name,
                None if notification.content.related_post_id is None else int(notification.content.related_post_id),
                None if notification.content.related_reply_id is None else int(notification.content.related_reply_id),
                notification.content.content_type,
                notification.content.content_text,
                notification.created_at.isoformat(),
                1 if notification.is_read else 0,
                None if notification.expires_at is None else notification.expires_at.isoformat(),
            ),
        )
        self._finalize_write()
        return copy.deepcopy(notification)

    def find_by_id(self, notification_id: NotificationId) -> Optional[Notification]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_notifications WHERE notification_id = ?",
            (int(notification_id),),
        )
        return self._hydrate(cur.fetchone())

    def find_by_ids(self, notification_ids: List[NotificationId]) -> List[Notification]:
        return [x for notification_id in notification_ids for x in [self.find_by_id(notification_id)] if x is not None]

    def delete(self, notification_id: NotificationId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_sns_notifications WHERE notification_id = ?",
            (int(notification_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[Notification]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_notifications ORDER BY created_at DESC, notification_id DESC"
        )
        return [x for row in cur.fetchall() for x in [self._hydrate(row)] if x is not None]

    def find_by_user_id(self, user_id: UserId, limit: int = 50, offset: int = 0) -> List[Notification]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_sns_notifications
            WHERE user_id = ?
            ORDER BY created_at DESC, notification_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(user_id), limit, offset),
        )
        return [x for row in cur.fetchall() for x in [self._hydrate(row)] if x is not None]

    def find_unread_by_user_id(self, user_id: UserId) -> List[Notification]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_sns_notifications
            WHERE user_id = ? AND is_read = 0
            ORDER BY created_at DESC, notification_id DESC
            """,
            (int(user_id),),
        )
        return [x for row in cur.fetchall() for x in [self._hydrate(row)] if x is not None]

    def mark_as_read(self, notification_id: NotificationId) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            "UPDATE game_sns_notifications SET is_read = 1 WHERE notification_id = ?",
            (int(notification_id),),
        )
        self._finalize_write()

    def mark_all_as_read(self, user_id: UserId) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            "UPDATE game_sns_notifications SET is_read = 1 WHERE user_id = ?",
            (int(user_id),),
        )
        self._finalize_write()

    def delete_expired_notifications(self, current_time: datetime) -> int:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            """
            DELETE FROM game_sns_notifications
            WHERE expires_at IS NOT NULL AND expires_at < ?
            """,
            (current_time.isoformat(),),
        )
        self._finalize_write()
        return cur.rowcount

    def delete_old_notifications(self, user_id: UserId, keep_count: int = 100) -> int:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            """
            SELECT notification_id
            FROM game_sns_notifications
            WHERE user_id = ? AND expires_at IS NULL
            ORDER BY created_at DESC, notification_id DESC
            """,
            (int(user_id),),
        )
        notification_ids = [int(row[0]) for row in cur.fetchall()]
        to_delete = notification_ids[keep_count:]
        for notification_id in to_delete:
            self._conn.execute(
                "DELETE FROM game_sns_notifications WHERE notification_id = ?",
                (notification_id,),
            )
        self._finalize_write()
        return len(to_delete)

    def get_unread_count(self, user_id: UserId) -> int:
        cur = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM game_sns_notifications
            WHERE user_id = ? AND is_read = 0
            """,
            (int(user_id),),
        )
        return int(cur.fetchone()[0])


__all__ = ["SqliteSnsNotificationRepository"]
