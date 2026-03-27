"""SQLite implementation of SNS post repository without pickle/BLOB snapshots."""

from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.repository.post_repository import PostRepository
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_state_codec import (
    build_post_aggregate,
)


class SqlitePostRepository(PostRepository):
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
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqlitePostRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqlitePostRepository":
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

    def _hashtags(self, post_id: PostId) -> List[str]:
        cur = self._conn.execute(
            """
            SELECT hashtag
            FROM game_sns_post_hashtags
            WHERE post_id = ?
            ORDER BY hashtag ASC
            """,
            (int(post_id),),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def _likes(self, post_id: PostId) -> List[tuple[int, str]]:
        cur = self._conn.execute(
            """
            SELECT user_id, created_at
            FROM game_sns_post_likes
            WHERE post_id = ?
            ORDER BY user_id ASC
            """,
            (int(post_id),),
        )
        return [(int(row[0]), str(row[1])) for row in cur.fetchall()]

    def _mentions(self, post_id: PostId) -> List[str]:
        cur = self._conn.execute(
            """
            SELECT user_name
            FROM game_sns_post_mentions
            WHERE post_id = ?
            ORDER BY user_name ASC
            """,
            (int(post_id),),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def _reply_ids(self, post_id: PostId) -> List[int]:
        cur = self._conn.execute(
            """
            SELECT reply_id
            FROM game_sns_replies
            WHERE parent_post_id = ?
            ORDER BY created_at ASC, reply_id ASC
            """,
            (int(post_id),),
        )
        return [int(row[0]) for row in cur.fetchall()]

    def _hydrate_post(self, row: sqlite3.Row | None) -> Optional[PostAggregate]:
        if row is None:
            return None
        post_id = PostId(int(row["post_id"]))
        return copy.deepcopy(
            build_post_aggregate(
                post_id=int(post_id),
                author_user_id=int(row["author_user_id"]),
                content=str(row["content"]),
                visibility=str(row["visibility"]),
                deleted=int(row["deleted"]),
                created_at=str(row["created_at"]),
                hashtags=self._hashtags(post_id),
                likes=self._likes(post_id),
                mentions=self._mentions(post_id),
                reply_ids=self._reply_ids(post_id),
            )
        )

    def _current_max_post_id(self) -> int:
        cur = self._conn.execute("SELECT COALESCE(MAX(post_id), 0) FROM game_sns_posts")
        return int(cur.fetchone()[0])

    def find_by_id(self, entity_id: PostId) -> Optional[PostAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_posts WHERE post_id = ?",
            (int(entity_id),),
        )
        return self._hydrate_post(cur.fetchone())

    def find_by_ids(self, entity_ids: List[PostId]) -> List[PostAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[PostAggregate]:
        cur = self._conn.execute("SELECT * FROM game_sns_posts ORDER BY post_id ASC")
        return [x for row in cur.fetchall() for x in [self._hydrate_post(row)] if x is not None]

    def save(self, entity: PostAggregate) -> PostAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(entity)
        self._conn.execute(
            """
            INSERT INTO game_sns_posts (
                post_id, author_user_id, content, visibility, deleted, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                author_user_id = excluded.author_user_id,
                content = excluded.content,
                visibility = excluded.visibility,
                deleted = excluded.deleted,
                created_at = excluded.created_at
            """,
            (
                int(entity.post_id),
                int(entity.author_user_id),
                entity.post_content.content,
                entity.post_content.visibility.value,
                1 if entity.deleted else 0,
                entity.created_at.isoformat(),
            ),
        )
        self._conn.execute("DELETE FROM game_sns_post_hashtags WHERE post_id = ?", (int(entity.post_id),))
        self._conn.execute("DELETE FROM game_sns_post_likes WHERE post_id = ?", (int(entity.post_id),))
        self._conn.execute("DELETE FROM game_sns_post_mentions WHERE post_id = ?", (int(entity.post_id),))
        self._conn.executemany(
            "INSERT INTO game_sns_post_hashtags (post_id, hashtag) VALUES (?, ?)",
            [(int(entity.post_id), hashtag) for hashtag in entity.post_content.hashtags],
        )
        self._conn.executemany(
            """
            INSERT INTO game_sns_post_likes (post_id, user_id, created_at)
            VALUES (?, ?, ?)
            """,
            [
                (int(entity.post_id), int(like.user_id), like.created_at.isoformat())
                for like in entity.likes
            ],
        )
        self._conn.executemany(
            "INSERT INTO game_sns_post_mentions (post_id, user_name) VALUES (?, ?)",
            [(int(entity.post_id), mention.mentioned_user_name) for mention in entity.mentions],
        )
        self._finalize_write()
        return copy.deepcopy(entity)

    def delete(self, entity_id: PostId) -> bool:
        self._assert_shared_transaction_active()
        self._conn.execute("DELETE FROM game_sns_post_hashtags WHERE post_id = ?", (int(entity_id),))
        self._conn.execute("DELETE FROM game_sns_post_likes WHERE post_id = ?", (int(entity_id),))
        self._conn.execute("DELETE FROM game_sns_post_mentions WHERE post_id = ?", (int(entity_id),))
        cur = self._conn.execute("DELETE FROM game_sns_posts WHERE post_id = ?", (int(entity_id),))
        self._finalize_write()
        return cur.rowcount > 0

    def generate_post_id(self) -> PostId:
        self._assert_shared_transaction_active()
        post_id = PostId(
            allocate_sequence_value(
                self._conn,
                "sns_post_id",
                initial_value=self._current_max_post_id(),
            )
        )
        self._finalize_write()
        return post_id

    def _load_query(self, sql: str, params: tuple[Any, ...]) -> List[PostAggregate]:
        cur = self._conn.execute(sql, params)
        return [x for row in cur.fetchall() for x in [self._hydrate_post(row)] if x is not None]

    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_posts
            WHERE author_user_id = ?
            ORDER BY created_at DESC, post_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(user_id), limit, offset),
        )

    def find_by_user_ids(
        self, user_ids: List[UserId], limit: int = 50, offset: int = 0, sort_by: str = "created_at"
    ) -> List[PostAggregate]:
        if not user_ids:
            return []
        placeholders = ",".join("?" for _ in user_ids)
        order_by = "created_at DESC, post_id DESC" if sort_by == "created_at" else "created_at DESC, post_id DESC"
        return self._load_query(
            f"""
            SELECT *
            FROM game_sns_posts
            WHERE author_user_id IN ({placeholders})
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            tuple(int(user_id) for user_id in user_ids) + (limit, offset),
        )

    def find_recent_posts(self, limit: int = 20) -> List[PostAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_posts
            ORDER BY created_at DESC, post_id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def find_posts_mentioning_user(self, user_name: str, limit: int = 20) -> List[PostAggregate]:
        return self._load_query(
            """
            SELECT p.*
            FROM game_sns_post_mentions m
            JOIN game_sns_posts p ON p.post_id = m.post_id
            WHERE m.user_name = ?
            ORDER BY p.created_at DESC, p.post_id DESC
            LIMIT ?
            """,
            (user_name, limit),
        )

    def find_liked_posts_by_user(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        return self._load_query(
            """
            SELECT p.*
            FROM game_sns_post_likes l
            JOIN game_sns_posts p ON p.post_id = l.post_id
            WHERE l.user_id = ?
            ORDER BY p.created_at DESC, p.post_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(user_id), limit, offset),
        )

    def find_posts_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[PostAggregate]:
        return self.find_liked_posts_by_user(user_id, limit=limit, offset=0)

    def search_posts_by_content(self, query: str, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        keyword = f"%{query.lower()}%"
        return self._load_query(
            """
            SELECT *
            FROM game_sns_posts
            WHERE LOWER(content) LIKE ?
            ORDER BY created_at DESC, post_id DESC
            LIMIT ? OFFSET ?
            """,
            (keyword, limit, offset),
        )

    def find_posts_by_hashtag(self, hashtag: str, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        return self._load_query(
            """
            SELECT p.*
            FROM game_sns_post_hashtags h
            JOIN game_sns_posts p ON p.post_id = h.post_id
            WHERE h.hashtag = ?
            ORDER BY p.created_at DESC, p.post_id DESC
            LIMIT ? OFFSET ?
            """,
            (hashtag, limit, offset),
        )

    def get_like_count(self, post_id: PostId) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM game_sns_post_likes WHERE post_id = ?",
            (int(post_id),),
        )
        return int(cur.fetchone()[0])

    def get_user_post_stats(self, user_id: UserId) -> Dict[str, int]:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM game_sns_posts WHERE author_user_id = ?",
            (int(user_id),),
        )
        total_posts = int(cur.fetchone()[0])
        cur = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM game_sns_post_likes l
            JOIN game_sns_posts p ON p.post_id = l.post_id
            WHERE p.author_user_id = ?
            """,
            (int(user_id),),
        )
        return {"total_posts": total_posts, "total_likes": int(cur.fetchone()[0])}

    def find_trending_posts(self, timeframe_hours: int = 24, limit: int = 10, offset: int = 0) -> List[PostAggregate]:
        cutoff = (datetime.now() - timedelta(hours=timeframe_hours)).isoformat()
        return self._load_query(
            """
            SELECT p.*
            FROM game_sns_posts p
            LEFT JOIN game_sns_post_likes l ON l.post_id = p.post_id
            WHERE p.created_at >= ?
            GROUP BY p.post_id
            ORDER BY COUNT(l.user_id) DESC, p.created_at DESC, p.post_id DESC
            LIMIT ? OFFSET ?
            """,
            (cutoff, limit, offset),
        )

    def bulk_delete_posts(self, post_ids: List[PostId], user_id: UserId) -> int:
        self._assert_shared_transaction_active()
        deleted = 0
        for post_id in post_ids:
            cur = self._conn.execute(
                "DELETE FROM game_sns_posts WHERE post_id = ? AND author_user_id = ?",
                (int(post_id), int(user_id)),
            )
            if cur.rowcount > 0:
                deleted += cur.rowcount
                self._conn.execute("DELETE FROM game_sns_post_hashtags WHERE post_id = ?", (int(post_id),))
                self._conn.execute("DELETE FROM game_sns_post_likes WHERE post_id = ?", (int(post_id),))
                self._conn.execute("DELETE FROM game_sns_post_mentions WHERE post_id = ?", (int(post_id),))
        self._finalize_write()
        return deleted

    def cleanup_deleted_posts(self, older_than_days: int = 30) -> int:
        self._assert_shared_transaction_active()
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        cur = self._conn.execute(
            "SELECT post_id FROM game_sns_posts WHERE deleted = 1 AND created_at < ?",
            (cutoff,),
        )
        post_ids = [int(row[0]) for row in cur.fetchall()]
        for post_id in post_ids:
            self._conn.execute("DELETE FROM game_sns_post_hashtags WHERE post_id = ?", (post_id,))
            self._conn.execute("DELETE FROM game_sns_post_likes WHERE post_id = ?", (post_id,))
            self._conn.execute("DELETE FROM game_sns_post_mentions WHERE post_id = ?", (post_id,))
            self._conn.execute("DELETE FROM game_sns_posts WHERE post_id = ?", (post_id,))
        self._finalize_write()
        return len(post_ids)

    def find_private_posts_by_user(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        return self._load_query(
            """
            SELECT *
            FROM game_sns_posts
            WHERE author_user_id = ? AND visibility = 'private'
            ORDER BY created_at DESC, post_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(user_id), limit, offset),
        )

    def find_posts_in_timeframe(self, timeframe_hours: int = 24, limit: int = 1000) -> List[PostAggregate]:
        cutoff = (datetime.now() - timedelta(hours=timeframe_hours)).isoformat()
        return self._load_query(
            """
            SELECT *
            FROM game_sns_posts
            WHERE created_at >= ?
            ORDER BY created_at DESC, post_id DESC
            LIMIT ?
            """,
            (cutoff, limit),
        )

    def exists_by_id(self, post_id: PostId) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM game_sns_posts WHERE post_id = ? LIMIT 1",
            (int(post_id),),
        )
        return cur.fetchone() is not None

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM game_sns_posts")
        return int(cur.fetchone()[0])

    def clear(self) -> None:
        self._assert_shared_transaction_active()
        for table_name in (
            "game_sns_post_mentions",
            "game_sns_post_likes",
            "game_sns_post_hashtags",
            "game_sns_posts",
        ):
            self._conn.execute(f"DELETE FROM {table_name}")
        self._finalize_write()


__all__ = ["SqlitePostRepository"]
