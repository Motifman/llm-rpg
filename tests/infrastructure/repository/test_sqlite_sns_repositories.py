"""SQLite SNS repository contract tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import (
    SqliteSnsUserRepository,
)
from tests.infrastructure.repository.test_post_repository_interface import (
    _TestPostRepositoryInterface,
)
from tests.infrastructure.repository.test_reply_repository_interface import (
    _TestReplyRepositoryInterface,
)
from tests.infrastructure.repository.test_sns_user_repository_interface import (
    _TestUserRepositoryInterface,
)


def _seed_social(
    conn: sqlite3.Connection,
) -> tuple[SqliteSnsUserRepository, SqlitePostRepository, SqliteReplyRepository]:
    user_repo = SqliteSnsUserRepository.for_standalone_connection(conn)
    post_repo = SqlitePostRepository.for_standalone_connection(conn)
    reply_repo = SqliteReplyRepository.for_standalone_connection(conn)
    store = InMemoryDataStore()
    for user in store.sns_users.values():
        user_repo.save(user)
    for post in store.posts.values():
        post_repo.save(post)
    for reply in store.replies.values():
        reply_repo.save(reply)
    return user_repo, post_repo, reply_repo


class TestSqliteUserRepository(_TestUserRepositoryInterface):
    @pytest.fixture
    def repository(self):
        conn = sqlite3.connect(":memory:")
        user_repo, _, _ = _seed_social(conn)
        return user_repo


class TestSqlitePostRepository(_TestPostRepositoryInterface):
    @pytest.fixture
    def repository(self):
        conn = sqlite3.connect(":memory:")
        _, post_repo, _ = _seed_social(conn)
        return post_repo


class TestSqliteReplyRepository(_TestReplyRepositoryInterface):
    @pytest.fixture
    def repository(self):
        conn = sqlite3.connect(":memory:")
        _, _, reply_repo = _seed_social(conn)
        return reply_repo


def test_sqlite_user_repository_specific_updates_profile_and_relationships() -> None:
    conn = sqlite3.connect(":memory:")
    user_repo, _, _ = _seed_social(conn)

    updated_user = user_repo.update_profile(user_id=user_repo.find_by_user_name("hero_user").user_id, bio="更新済み", display_name="新勇者")
    assert updated_user.get_user_profile_info()["bio"] == "更新済み"
    assert updated_user.get_user_profile_info()["display_name"] == "新勇者"


def test_sqlite_user_repository_cleanup_broken_relationships() -> None:
    conn = sqlite3.connect(":memory:")
    user_repo, _, _ = _seed_social(conn)

    conn.execute(
        """
        INSERT INTO game_sns_follows (follower_user_id, followee_user_id, created_at)
        VALUES (999, 1, '2026-01-01T00:00:00')
        """
    )
    cleaned = user_repo.cleanup_broken_relationships()
    assert cleaned >= 1
