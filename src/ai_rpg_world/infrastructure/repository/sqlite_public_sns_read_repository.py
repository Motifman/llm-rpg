"""公開SNSの候補をSQLの件数上限付きで読み、関連集合を復元しない。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ai_rpg_world.application.social.public_sns.contracts import ContentKind
from ai_rpg_world.application.social.public_sns.read_repository import PublicSnsContentRecord, PublicSnsUserRecord
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility
from ai_rpg_world.domain.sns.value_object.sns_identity_token import SnsIdentityToken
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import get_sns_public_namespace
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import SqliteSnsNotificationRepository

_CONTENT_COLUMNS = "identity_token, author_user_id, author_identity_token, content, visibility, deleted, created_at"


def _validate_limit(limit: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 101:
        raise ValueError("取得件数は1から101までの整数で指定してください")


def _source(kind: ContentKind) -> tuple[str, str]:
    if kind == "post":
        return "game_sns_posts", (
            f"post_id AS local_id, {_CONTENT_COLUMNS}, NULL AS parent_post_id, "
            "NULL AS parent_reply_id, NULL AS parent_identity_token"
        )
    if kind == "reply":
        return (
            "game_sns_replies",
            f"reply_id AS local_id, {_CONTENT_COLUMNS}, parent_post_id, parent_reply_id, parent_identity_token",
        )
    raise ValueError("対象種別はpostまたはreplyで指定してください")


class SqlitePublicSnsReadRepository:
    """閲覧可否は上位層へ委ね、内部整数ID降順の候補だけを返す。"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        self._notifications = SqliteSnsNotificationRepository(
            connection,
            _commits_after_write=False,
            _initialize_schema=False,
        )

    @property
    def namespace(self) -> str:
        return SnsIdentityToken(get_sns_public_namespace(self._conn)).value

    def find_user(self, user_id: int) -> PublicSnsUserRecord | None:
        row = self._conn.execute(
            "SELECT user_id, identity_token, display_name FROM game_sns_users WHERE user_id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return PublicSnsUserRecord(
            user_id=int(row["user_id"]),
            identity_token=SnsIdentityToken(row["identity_token"]).value,
            display_name=str(row["display_name"]),
        )

    def has_block(self, blocker_user_id: int, blocked_user_id: int) -> bool:
        return (
            self._conn.execute(
                "SELECT 1 FROM game_sns_blocks WHERE blocker_user_id = ? AND blocked_user_id = ? LIMIT 1",
                (blocker_user_id, blocked_user_id),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _record(kind: ContentKind, row: sqlite3.Row) -> PublicSnsContentRecord:
        parent_kind: ContentKind | None = None
        parent_id = None
        if row["parent_reply_id"] is not None and row["parent_post_id"] is None:
            parent_kind, parent_id = "reply", int(row["parent_reply_id"])
        elif row["parent_post_id"] is not None and row["parent_reply_id"] is None:
            parent_kind, parent_id = "post", int(row["parent_post_id"])
        return PublicSnsContentRecord(
            kind=kind,
            local_id=int(row["local_id"]),
            identity_token=SnsIdentityToken(row["identity_token"]).value,
            author_user_id=int(row["author_user_id"]),
            content=str(row["content"]),
            visibility=PostVisibility(row["visibility"]),
            deleted=bool(row["deleted"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            parent_kind=parent_kind,
            parent_id=parent_id,
            author_identity_token=row["author_identity_token"],
            parent_identity_token=row["parent_identity_token"],
        )

    def find_content(self, kind: ContentKind, identity_token: str) -> PublicSnsContentRecord | None:
        table, columns = _source(kind)
        row = self._conn.execute(
            f"SELECT {columns} FROM {table} WHERE identity_token = ? LIMIT 1",
            (identity_token,),
        ).fetchone()
        return None if row is None else self._record(kind, row)

    def find_content_by_id(self, kind: ContentKind, local_id: int) -> PublicSnsContentRecord | None:
        table, columns = _source(kind)
        row = self._conn.execute(
            f"SELECT {columns} FROM {table} WHERE {kind}_id = ? LIMIT 1",
            (local_id,),
        ).fetchone()
        return None if row is None else self._record(kind, row)

    def scan_posts(self, before_id: int | None, limit: int) -> list[PublicSnsContentRecord]:
        _validate_limit(limit)
        table, columns = _source("post")
        where = "" if before_id is None else "WHERE post_id < ? "
        parameters = (limit,) if before_id is None else (before_id, limit)
        rows = self._conn.execute(
            f"SELECT {columns} FROM {table} {where}ORDER BY post_id DESC LIMIT ?",
            parameters,
        )
        return [self._record("post", row) for row in rows]

    def scan_replies(
        self,
        parent_kind: ContentKind,
        parent_id: int,
        before_id: int | None,
        limit: int,
    ) -> list[PublicSnsContentRecord]:
        _validate_limit(limit)
        _source(parent_kind)
        table, columns = _source("reply")
        other_parent = "reply" if parent_kind == "post" else "post"
        where = f"WHERE parent_{parent_kind}_id = ? AND parent_{other_parent}_id IS NULL "
        parameters: tuple[int, ...] = (parent_id, limit)
        if before_id is not None:
            where += "AND reply_id < ? "
            parameters = (parent_id, before_id, limit)
        rows = self._conn.execute(
            f"SELECT {columns} FROM {table} {where}ORDER BY reply_id DESC LIMIT ?",
            parameters,
        )
        return [self._record("reply", row) for row in rows]

    def scan_notifications(
        self,
        viewer_user_id: int,
        before_id: int | None,
        limit: int,
    ) -> list[Notification]:
        _validate_limit(limit)
        where = "WHERE user_id = ? "
        parameters: tuple[int, ...] = (viewer_user_id, limit)
        if before_id is not None:
            where += "AND notification_id < ? "
            parameters = (viewer_user_id, before_id, limit)
        rows = self._conn.execute(
            f"SELECT * FROM game_sns_notifications {where}ORDER BY notification_id DESC LIMIT ?",
            parameters,
        )
        return [notification for row in rows if (notification := self._notifications._hydrate(row)) is not None]
