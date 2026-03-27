"""SQLite implementation of SNS user repository without pickle/BLOB snapshots."""

from __future__ import annotations

import copy
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_state_codec import (
    build_user_aggregate,
)


class SqliteSnsUserRepository(UserRepository):
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
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteSnsUserRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteSnsUserRepository":
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

    def _relation_rows(
        self,
        table_name: str,
        lhs_column: str,
        rhs_column: str,
        user_id: UserId,
    ) -> List[tuple[int, int, str]]:
        cur = self._conn.execute(
            f"""
            SELECT {lhs_column}, {rhs_column}, created_at
            FROM {table_name}
            WHERE {lhs_column} = ?
            ORDER BY {rhs_column} ASC
            """,
            (int(user_id),),
        )
        return [(int(row[0]), int(row[1]), str(row[2])) for row in cur.fetchall()]

    def _current_max_user_id(self) -> int:
        cur = self._conn.execute("SELECT COALESCE(MAX(user_id), 0) FROM game_sns_users")
        return int(cur.fetchone()[0])

    def _hydrate_user_from_row(self, row: sqlite3.Row | None) -> Optional[UserAggregate]:
        if row is None:
            return None
        user_id = UserId(int(row["user_id"]))
        return copy.deepcopy(
            build_user_aggregate(
                user_id=int(user_id),
                user_name=str(row["user_name"]),
                display_name=str(row["display_name"]),
                bio=str(row["bio"]),
                follows=self._relation_rows(
                    "game_sns_follows", "follower_user_id", "followee_user_id", user_id
                ),
                blocks=self._relation_rows(
                    "game_sns_blocks", "blocker_user_id", "blocked_user_id", user_id
                ),
                subscriptions=self._relation_rows(
                    "game_sns_subscriptions",
                    "subscriber_user_id",
                    "subscribed_user_id",
                    user_id,
                ),
            )
        )

    def find_by_id(self, entity_id: UserId) -> Optional[UserAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_users WHERE user_id = ?",
            (int(entity_id),),
        )
        return self._hydrate_user_from_row(cur.fetchone())

    def find_by_ids(self, entity_ids: List[UserId]) -> List[UserAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[UserAggregate]:
        cur = self._conn.execute("SELECT * FROM game_sns_users ORDER BY user_id ASC")
        return [x for row in cur.fetchall() for x in [self._hydrate_user_from_row(row)] if x is not None]

    def save(self, entity: UserAggregate) -> UserAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(entity)
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        profile = entity.get_user_profile_info()
        try:
            self._conn.execute(
                """
                INSERT INTO game_sns_users (user_id, user_name, display_name, bio)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    user_name = excluded.user_name,
                    display_name = excluded.display_name,
                    bio = excluded.bio
                """,
                (
                    int(entity.user_id),
                    profile["user_name"],
                    profile["display_name"],
                    profile["bio"],
                ),
            )
            self._conn.execute(
                "DELETE FROM game_sns_follows WHERE follower_user_id = ?",
                (int(entity.user_id),),
            )
            self._conn.execute(
                "DELETE FROM game_sns_blocks WHERE blocker_user_id = ?",
                (int(entity.user_id),),
            )
            self._conn.execute(
                "DELETE FROM game_sns_subscriptions WHERE subscriber_user_id = ?",
                (int(entity.user_id),),
            )
            self._conn.executemany(
                """
                INSERT INTO game_sns_follows (follower_user_id, followee_user_id, created_at)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        int(rel.follower_user_id),
                        int(rel.followee_user_id),
                        rel.created_at.isoformat(),
                    )
                    for rel in entity.follow_relationships
                ],
            )
            self._conn.executemany(
                """
                INSERT INTO game_sns_blocks (blocker_user_id, blocked_user_id, created_at)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        int(rel.blocker_user_id),
                        int(rel.blocked_user_id),
                        rel.created_at.isoformat(),
                    )
                    for rel in entity.block_relationships
                ],
            )
            self._conn.executemany(
                """
                INSERT INTO game_sns_subscriptions (
                    subscriber_user_id, subscribed_user_id, created_at
                ) VALUES (?, ?, ?)
                """,
                [
                    (
                        int(rel.subscriber_user_id),
                        int(rel.subscribed_user_id),
                        rel.created_at.isoformat(),
                    )
                    for rel in entity.subscribe_relationships
                ],
            )
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return copy.deepcopy(entity)

    def delete(self, entity_id: UserId) -> bool:
        self._assert_shared_transaction_active()
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        try:
            self._conn.execute(
                "DELETE FROM game_sns_follows WHERE follower_user_id = ? OR followee_user_id = ?",
                (int(entity_id), int(entity_id)),
            )
            self._conn.execute(
                "DELETE FROM game_sns_blocks WHERE blocker_user_id = ? OR blocked_user_id = ?",
                (int(entity_id), int(entity_id)),
            )
            self._conn.execute(
                """
                DELETE FROM game_sns_subscriptions
                WHERE subscriber_user_id = ? OR subscribed_user_id = ?
                """,
                (int(entity_id), int(entity_id)),
            )
            cur = self._conn.execute(
                "DELETE FROM game_sns_users WHERE user_id = ?",
                (int(entity_id),),
            )
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return cur.rowcount > 0

    def find_by_user_name(self, user_name: str) -> Optional[UserAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_users WHERE user_name = ?",
            (user_name,),
        )
        return self._hydrate_user_from_row(cur.fetchone())

    def find_by_display_name(self, display_name: str) -> Optional[UserAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_sns_users WHERE display_name = ?",
            (display_name,),
        )
        return self._hydrate_user_from_row(cur.fetchone())

    def find_followers(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT follower_user_id
            FROM game_sns_follows
            WHERE followee_user_id = ?
            ORDER BY follower_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def find_followees(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT followee_user_id
            FROM game_sns_follows
            WHERE follower_user_id = ?
            ORDER BY followee_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def find_mutual_follows(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT f1.followee_user_id
            FROM game_sns_follows f1
            JOIN game_sns_follows f2
              ON f1.followee_user_id = f2.follower_user_id
             AND f2.followee_user_id = f1.follower_user_id
            WHERE f1.follower_user_id = ?
            ORDER BY f1.followee_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def count_followers(self, user_id: UserId) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM game_sns_follows WHERE followee_user_id = ?",
            (int(user_id),),
        )
        return int(cur.fetchone()[0])

    def count_followees(self, user_id: UserId) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM game_sns_follows WHERE follower_user_id = ?",
            (int(user_id),),
        )
        return int(cur.fetchone()[0])

    def find_blocked_users(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT blocked_user_id
            FROM game_sns_blocks
            WHERE blocker_user_id = ?
            ORDER BY blocked_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def find_blockers(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT blocker_user_id
            FROM game_sns_blocks
            WHERE blocked_user_id = ?
            ORDER BY blocker_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def is_blocked(self, blocker_user_id: UserId, blocked_user_id: UserId) -> bool:
        cur = self._conn.execute(
            """
            SELECT 1
            FROM game_sns_blocks
            WHERE blocker_user_id = ? AND blocked_user_id = ?
            LIMIT 1
            """,
            (int(blocker_user_id), int(blocked_user_id)),
        )
        return cur.fetchone() is not None

    def find_subscribers(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT subscriber_user_id
            FROM game_sns_subscriptions
            WHERE subscribed_user_id = ?
            ORDER BY subscriber_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def find_subscriptions(self, user_id: UserId) -> List[UserId]:
        cur = self._conn.execute(
            """
            SELECT subscribed_user_id
            FROM game_sns_subscriptions
            WHERE subscriber_user_id = ?
            ORDER BY subscribed_user_id ASC
            """,
            (int(user_id),),
        )
        return [UserId(int(row[0])) for row in cur.fetchall()]

    def is_subscribed(self, subscriber_user_id: UserId, subscribed_user_id: UserId) -> bool:
        cur = self._conn.execute(
            """
            SELECT 1
            FROM game_sns_subscriptions
            WHERE subscriber_user_id = ? AND subscribed_user_id = ?
            LIMIT 1
            """,
            (int(subscriber_user_id), int(subscribed_user_id)),
        )
        return cur.fetchone() is not None

    def update_profile(self, user_id: UserId, bio: str, display_name: str) -> UserAggregate:
        self._assert_shared_transaction_active()
        user = self.find_by_id(user_id)
        if user is None:
            raise ValueError(f"user not found: {user_id}")
        user.update_user_profile(bio, display_name)
        return self.save(user)

    def search_users(self, query: str, limit: int = 20) -> List[UserAggregate]:
        keyword = f"%{query.lower()}%"
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_sns_users
            WHERE LOWER(user_name) LIKE ?
               OR LOWER(display_name) LIKE ?
               OR LOWER(bio) LIKE ?
            ORDER BY user_id ASC
            LIMIT ?
            """,
            (keyword, keyword, keyword, limit),
        )
        return [x for row in cur.fetchall() for x in [self._hydrate_user_from_row(row)] if x is not None]

    def get_user_stats(self, user_id: UserId) -> Dict[str, int]:
        return {
            "follower_count": self.count_followers(user_id),
            "followee_count": self.count_followees(user_id),
            "blocked_count": len(self.find_blocked_users(user_id)),
            "subscription_count": len(self.find_subscriptions(user_id)),
            "subscriber_count": len(self.find_subscribers(user_id)),
        }

    def bulk_update_relationships(self, relationships: List[Tuple[UserId, UserId, str]]) -> int:
        self._assert_shared_transaction_active()
        updated_count = 0
        seen_users: Dict[UserId, UserAggregate] = {}
        for from_user_id, to_user_id, relationship_type in relationships:
            user = seen_users.get(from_user_id)
            if user is None:
                user = self.find_by_id(from_user_id)
                if user is None or self.find_by_id(to_user_id) is None:
                    continue
                seen_users[from_user_id] = user
            if relationship_type == "follow":
                user.follow(to_user_id)
                updated_count += 1
            elif relationship_type == "block":
                user.block(to_user_id)
                updated_count += 1
            elif relationship_type == "subscribe":
                user.subscribe(to_user_id)
                updated_count += 1
        for user in seen_users.values():
            self.save(user)
        return updated_count

    def cleanup_broken_relationships(self) -> int:
        self._assert_shared_transaction_active()
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        removed = 0
        try:
            for table_name, lhs_column, rhs_column in (
                ("game_sns_follows", "follower_user_id", "followee_user_id"),
                ("game_sns_blocks", "blocker_user_id", "blocked_user_id"),
                ("game_sns_subscriptions", "subscriber_user_id", "subscribed_user_id"),
            ):
                cur = self._conn.execute(
                    f"""
                    DELETE FROM {table_name}
                    WHERE {lhs_column} NOT IN (SELECT user_id FROM game_sns_users)
                       OR {rhs_column} NOT IN (SELECT user_id FROM game_sns_users)
                    """
                )
                removed += cur.rowcount
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return removed

    def find_users_by_ids(self, user_ids: List[UserId]) -> List[UserAggregate]:
        return self.find_by_ids(user_ids)

    def generate_user_id(self) -> UserId:
        self._assert_shared_transaction_active()
        user_id = UserId(
            allocate_sequence_value(
                self._conn,
                "sns_user_id",
                initial_value=self._current_max_user_id(),
            )
        )
        self._finalize_write()
        return user_id

    def exists_by_id(self, user_id: UserId) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM game_sns_users WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        )
        return cur.fetchone() is not None

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM game_sns_users")
        return int(cur.fetchone()[0])

    def clear(self) -> None:
        self._assert_shared_transaction_active()
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        try:
            for table_name in (
                "game_sns_subscriptions",
                "game_sns_blocks",
                "game_sns_follows",
                "game_sns_users",
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


__all__ = ["SqliteSnsUserRepository"]
