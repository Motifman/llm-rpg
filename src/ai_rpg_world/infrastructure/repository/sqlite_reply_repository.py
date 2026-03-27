"""SQLite implementation of SNS reply repository without pickle/BLOB snapshots."""

from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.repository.reply_repository import ReplyRepository
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_state_codec import (
    build_reply_aggregate,
)


class SqliteReplyRepository(ReplyRepository):
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
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteReplyRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteReplyRepository":
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

    def _hashtags(self, reply_id: ReplyId) -> List[str]:
        cur = self._conn.execute(
            """
            SELECT hashtag
            FROM game_sns_reply_hashtags
            WHERE reply_id = ?
            ORDER BY hashtag ASC
            """,
            (int(reply_id),),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def _likes(self, reply_id: ReplyId) -> List[tuple[int, str]]:
        cur = self._conn.execute(
            """
            SELECT user_id, created_at
            FROM game_sns_reply_likes
            WHERE reply_id = ?
            ORDER BY user_id ASC
            """,
            (int(reply_id),),
        )
        return [(int(row[0]), str(row[1])) for row in cur.fetchall()]

    def _mentions(self, reply_id: ReplyId) -> List[str]:
        cur = self._conn.execute(
            """
            SELECT user_name
            FROM game_sns_reply_mentions
            WHERE reply_id = ?
            ORDER BY user_name ASC
            """,
            (int(reply_id),),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def _child_reply_ids(self, reply_id: ReplyId) -> List[int]:
        cur = self._conn.execute(
            """
            SELECT reply_id
            FROM game_sns_replies
            WHERE parent_reply_id = ?
            ORDER BY created_at ASC, reply_id ASC
            """,
            (int(reply_id),),
        )
        return [int(row[0]) for row in cur.fetchall()]

    def _hydrate_reply(self, row: sqlite3.Row | None) -> Optional[ReplyAggregate]:
        if row is None:
            return None
        reply_id = ReplyId(int(row["reply_id"]))
        return copy.deepcopy(
            build_reply_aggregate(
                reply_id=int(reply_id),
                author_user_id=int(row["author_user_id"]),
                parent_post_id=None if row["parent_post_id"] is None else int(row["parent_post_id"]),
                parent_reply_id=None if row["parent_reply_id"] is None else int(row["parent_reply_id"]),
                content=str(row["content"]),
                visibility=str(row["visibility"]),
                deleted=int(row["deleted"]),
                created_at=str(row["created_at"]),
                hashtags=self._hashtags(reply_id),
                likes=self._likes(reply_id),
                mentions=self._mentions(reply_id),
                child_reply_ids=self._child_reply_ids(reply_id),
            )
        )

    def _current_max_reply_id(self) -> int:
        cur = self._conn.execute("SELECT COALESCE(MAX(reply_id), 0) FROM game_sns_replies")
        return int(cur.fetchone()[0])

    def find_by_id(self, reply_id: ReplyId) -> Optional[ReplyAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_replies WHERE reply_id = ?",
            (int(reply_id),),
        )
        return self._hydrate_reply(cur.fetchone())

    def find_by_ids(self, entity_ids: List[Union[int, ReplyId]]) -> List[ReplyAggregate]:
        normalized = [ReplyId(entity_id) if isinstance(entity_id, int) else entity_id for entity_id in entity_ids]
        return [x for entity_id in normalized for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[ReplyAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_replies WHERE deleted = 0 ORDER BY reply_id ASC"
        )
        return [x for row in cur.fetchall() for x in [self._hydrate_reply(row)] if x is not None]

    def save(self, reply: ReplyAggregate) -> ReplyAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(reply)
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        try:
            self._conn.execute(
                """
                INSERT INTO game_sns_replies (
                    reply_id,
                    author_user_id,
                    parent_post_id,
                    parent_reply_id,
                    content,
                    visibility,
                    deleted,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(reply_id) DO UPDATE SET
                    author_user_id = excluded.author_user_id,
                    parent_post_id = excluded.parent_post_id,
                    parent_reply_id = excluded.parent_reply_id,
                    content = excluded.content,
                    visibility = excluded.visibility,
                    deleted = excluded.deleted,
                    created_at = excluded.created_at
                """,
                (
                    int(reply.reply_id),
                    int(reply.author_user_id),
                    None if reply.parent_post_id is None else int(reply.parent_post_id),
                    None if reply.parent_reply_id is None else int(reply.parent_reply_id),
                    reply.content.content,
                    reply.content.visibility.value,
                    1 if reply.deleted else 0,
                    reply.created_at.isoformat(),
                ),
            )
            self._conn.execute("DELETE FROM game_sns_reply_hashtags WHERE reply_id = ?", (int(reply.reply_id),))
            self._conn.execute("DELETE FROM game_sns_reply_likes WHERE reply_id = ?", (int(reply.reply_id),))
            self._conn.execute("DELETE FROM game_sns_reply_mentions WHERE reply_id = ?", (int(reply.reply_id),))
            self._conn.executemany(
                "INSERT INTO game_sns_reply_hashtags (reply_id, hashtag) VALUES (?, ?)",
                [(int(reply.reply_id), hashtag) for hashtag in reply.content.hashtags],
            )
            self._conn.executemany(
                """
                INSERT INTO game_sns_reply_likes (reply_id, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                [
                    (int(reply.reply_id), int(like.user_id), like.created_at.isoformat())
                    for like in reply.likes
                ],
            )
            self._conn.executemany(
                "INSERT INTO game_sns_reply_mentions (reply_id, user_name) VALUES (?, ?)",
                [(int(reply.reply_id), mention.mentioned_user_name) for mention in reply.mentions],
            )
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return copy.deepcopy(reply)

    def delete(self, entity_id: ReplyId) -> bool:
        self._assert_shared_transaction_active()
        reply = self.find_by_id(entity_id)
        if reply is None or reply.deleted:
            return False
        reply.delete(reply.author_user_id, "reply")
        self.save(reply)
        return True

    def generate_reply_id(self) -> ReplyId:
        self._assert_shared_transaction_active()
        reply_id = ReplyId(
            allocate_sequence_value(
                self._conn,
                "sns_reply_id",
                initial_value=self._current_max_reply_id(),
            )
        )
        self._finalize_write()
        return reply_id

    def _load_query(self, sql: str, params: tuple[Any, ...]) -> List[ReplyAggregate]:
        cur = self._conn.execute(sql, params)
        return [x for row in cur.fetchall() for x in [self._hydrate_reply(row)] if x is not None]

    def find_by_post_id(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_replies
            WHERE parent_post_id = ? AND deleted = 0
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(post_id), limit, offset),
        )

    def find_by_post_id_include_deleted(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_replies
            WHERE parent_post_id = ?
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(post_id), limit, offset),
        )

    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_replies
            WHERE author_user_id = ? AND deleted = 0
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(user_id), limit, offset),
        )

    def find_by_parent_reply_id(self, parent_reply_id: ReplyId, limit: int = 20) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_replies
            WHERE parent_reply_id = ? AND deleted = 0
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ?
            """,
            (int(parent_reply_id), limit),
        )

    def find_replies_mentioning_user(self, user_name: str, limit: int = 20) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT r.*
            FROM game_sns_reply_mentions m
            JOIN game_sns_replies r ON r.reply_id = m.reply_id
            WHERE m.user_name = ? AND r.deleted = 0
            ORDER BY r.created_at DESC, r.reply_id DESC
            LIMIT ?
            """,
            (user_name, limit),
        )

    def find_replies_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT r.*
            FROM game_sns_reply_likes l
            JOIN game_sns_replies r ON r.reply_id = l.reply_id
            WHERE l.user_id = ? AND r.deleted = 0
            ORDER BY r.created_at DESC, r.reply_id DESC
            LIMIT ?
            """,
            (int(user_id), limit),
        )

    def find_replies_with_parent_posts(self, limit: int = 20) -> List[tuple]:
        cur = self._conn.execute(
            """
            SELECT r.reply_id, r.parent_post_id, p.post_id
            FROM game_sns_replies r
            LEFT JOIN game_sns_posts p ON p.post_id = r.parent_post_id
            WHERE r.deleted = 0
            ORDER BY r.created_at DESC, r.reply_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [(int(row[0]), None if row[1] is None else int(row[1]), row[2]) for row in cur.fetchall()]

    def search_replies_by_content(self, query: str, limit: int = 20) -> List[ReplyAggregate]:
        keyword = f"%{query.lower()}%"
        return self._load_query(
            """
            SELECT *
            FROM game_sns_replies
            WHERE deleted = 0 AND LOWER(content) LIKE ?
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ?
            """,
            (keyword, limit),
        )

    def get_reply_count(self, post_id: PostId) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM game_sns_replies WHERE parent_post_id = ? AND deleted = 0",
            (int(post_id),),
        )
        return int(cur.fetchone()[0])

    def _collect_thread_replies(
        self,
        parent_id: Union[PostId, ReplyId],
        current_depth: int,
        max_depth: int,
        include_deleted: bool,
        result: Dict[Union[PostId, ReplyId], List[ReplyAggregate]],
    ) -> None:
        if current_depth > max_depth:
            return
        if isinstance(parent_id, PostId):
            replies = self.find_by_post_id_include_deleted(parent_id, limit=1000, offset=0) if include_deleted else self.find_by_post_id(parent_id, limit=1000, offset=0)
        else:
            if include_deleted:
                replies = self._load_query(
                    """
                    SELECT *
                    FROM game_sns_replies
                    WHERE parent_reply_id = ?
                    ORDER BY created_at ASC, reply_id ASC
                    """,
                    (int(parent_id),),
                )
            else:
                replies = self._load_query(
                    """
                    SELECT *
                    FROM game_sns_replies
                    WHERE parent_reply_id = ? AND deleted = 0
                    ORDER BY created_at ASC, reply_id ASC
                    """,
                    (int(parent_id),),
                )
        replies.sort(key=lambda reply: reply.created_at)
        result[parent_id] = replies
        for reply in replies:
            self._collect_thread_replies(reply.reply_id, current_depth + 1, max_depth, include_deleted, result)

    def find_thread_replies(self, root_post_id: PostId, max_depth: int = 3) -> Dict[PostId, List[ReplyAggregate]]:
        result: Dict[Union[PostId, ReplyId], List[ReplyAggregate]] = {}
        self._collect_thread_replies(root_post_id, 0, max_depth, False, result)
        return result  # type: ignore[return-value]

    def find_thread_replies_include_deleted(self, root_post_id: PostId, max_depth: int = 3) -> Dict[PostId, List[ReplyAggregate]]:
        result: Dict[Union[PostId, ReplyId], List[ReplyAggregate]] = {}
        self._collect_thread_replies(root_post_id, 0, max_depth, True, result)
        return result  # type: ignore[return-value]

    def find_replies_by_post_ids(self, post_ids: List[PostId]) -> Dict[PostId, List[ReplyAggregate]]:
        return {post_id: self.find_by_post_id(post_id, limit=1000, offset=0) for post_id in post_ids}

    def get_user_reply_stats(self, user_id: UserId) -> Dict[str, int]:
        cur = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM game_sns_replies
            WHERE author_user_id = ? AND deleted = 0
            """,
            (int(user_id),),
        )
        total_replies = int(cur.fetchone()[0])
        cur = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM game_sns_reply_likes l
            JOIN game_sns_replies r ON r.reply_id = l.reply_id
            WHERE r.author_user_id = ? AND r.deleted = 0
            """,
            (int(user_id),),
        )
        total_likes_received = int(cur.fetchone()[0])
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        cur = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM game_sns_replies
            WHERE author_user_id = ? AND deleted = 0 AND created_at >= ?
            """,
            (int(user_id), cutoff),
        )
        return {
            "total_replies": total_replies,
            "total_likes_received": total_likes_received,
            "replies_this_month": int(cur.fetchone()[0]),
        }

    def find_recent_replies(self, limit: int = 20) -> List[ReplyAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_replies
            WHERE deleted = 0
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def find_replies_excluding_blocked_users(
        self,
        user_id: UserId,
        blocked_user_ids: List[UserId],
        limit: int = 20,
    ) -> List[ReplyAggregate]:
        if not blocked_user_ids:
            return self.find_recent_replies(limit=limit)
        placeholders = ",".join("?" for _ in blocked_user_ids)
        return self._load_query(
            f"""
            SELECT *
            FROM game_sns_replies
            WHERE deleted = 0 AND author_user_id NOT IN ({placeholders})
            ORDER BY created_at DESC, reply_id DESC
            LIMIT ?
            """,
            tuple(int(blocked_user_id) for blocked_user_id in blocked_user_ids) + (limit,),
        )

    def bulk_delete_replies(self, reply_ids: List[ReplyId], user_id: UserId) -> int:
        self._assert_shared_transaction_active()
        deleted = 0
        for reply_id in reply_ids:
            reply = self.find_by_id(reply_id)
            if reply is None or reply.author_user_id != user_id or reply.deleted:
                continue
            reply.delete(user_id, "reply")
            self.save(reply)
            deleted += 1
        return deleted

    def cleanup_deleted_replies(self, older_than_days: int = 30) -> int:
        self._assert_shared_transaction_active()
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        try:
            cur = self._conn.execute(
                "SELECT reply_id FROM game_sns_replies WHERE deleted = 1 AND created_at < ?",
                (cutoff,),
            )
            reply_ids = [int(row[0]) for row in cur.fetchall()]
            for reply_id in reply_ids:
                self._conn.execute("DELETE FROM game_sns_reply_hashtags WHERE reply_id = ?", (reply_id,))
                self._conn.execute("DELETE FROM game_sns_reply_likes WHERE reply_id = ?", (reply_id,))
                self._conn.execute("DELETE FROM game_sns_reply_mentions WHERE reply_id = ?", (reply_id,))
                self._conn.execute("DELETE FROM game_sns_replies WHERE reply_id = ?", (reply_id,))
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return len(reply_ids)

    def clear(self) -> None:
        self._assert_shared_transaction_active()
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        try:
            for table_name in (
                "game_sns_reply_mentions",
                "game_sns_reply_likes",
                "game_sns_reply_hashtags",
                "game_sns_replies",
            ):
                self._conn.execute(f"DELETE FROM {table_name}")
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise


__all__ = ["SqliteReplyRepository"]
