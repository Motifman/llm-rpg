"""公開参照の識別子を保存・復元・分岐で失わないことを保証する。"""

import sqlite3
from uuid import UUID

import pytest

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.exception.identity_token_exception import SnsIdentityValidationException
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId
from ai_rpg_world.infrastructure.repository import game_write_sqlite_schema as schema
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.sqlite_migration import apply_migrations
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository


def _post(number: int = 1) -> PostAggregate:
    return PostAggregate.create(PostId(number), UserId(1), PostContent("投稿"))


def _reply(number: int = 1) -> ReplyAggregate:
    return ReplyAggregate.create(
        ReplyId(number), PostId(1), None, UserId(1), UserId(2), PostContent("返信")
    )


def _user(number: int = 1) -> UserAggregate:
    return UserAggregate.create_new_user(UserId(number), f"hero_{number}", "勇者", "")


@pytest.mark.parametrize("repository_type,create", [
    (SqlitePostRepository, _post), (SqliteReplyRepository, _reply),
])
def test_sqlite_identity_survives_reopen_and_state_changes(tmp_path, repository_type, create) -> None:
    """接続を開き直していいねや削除を保存しても、投稿と返信の識別子は変わらない。"""
    path = tmp_path / "social.sqlite"
    content = create()
    with sqlite3.connect(path) as connection:
        repository_type.for_standalone_connection(connection).save(content)
    with sqlite3.connect(path) as connection:
        repository = repository_type.for_standalone_connection(connection)
        restored = repository.find_by_id(content.content_id)
        assert restored.identity_token == content.identity_token
        restored.like(UserId(3), restored.get_content_type())
        restored.delete(restored.author_user_id, restored.get_content_type())
        repository.save(restored)
        assert repository.find_by_id(content.content_id).identity_token == content.identity_token


def test_memory_snapshot_preserves_namespace_and_existing_identities() -> None:
    """保存領域の復元では既存の識別子を維持し、分岐後の同じ整数には別の識別子を使う。"""
    original = InMemoryDataStore()
    snapshot = original.take_snapshot()
    branch = InMemoryDataStore()
    assert original.sns_public_namespace != branch.sns_public_namespace
    branch.restore_snapshot(snapshot)
    assert branch.sns_public_namespace == original.sns_public_namespace
    assert branch.posts[PostId(1)].identity_token == original.posts[PostId(1)].identity_token
    assert branch.replies[ReplyId(1)].identity_token == original.replies[ReplyId(1)].identity_token
    assert branch.sns_users[UserId(1)].identity_token == original.sns_users[UserId(1)].identity_token
    original.posts[PostId(1)] = _post()
    branch.posts[PostId(1)] = _post()
    assert original.posts[PostId(1)].identity_token != branch.posts[PostId(1)].identity_token


def test_sqlite_namespace_persists_across_reopen_and_differs_for_new_storage(tmp_path) -> None:
    """同じデータベースを開き直すと名前空間は不変で、別データベースには別の値を発行する。"""
    path = tmp_path / "social.sqlite"
    with sqlite3.connect(path) as connection:
        schema.init_game_write_schema(connection)
        namespace = schema.get_sns_public_namespace(connection)
        assert UUID(hex=namespace).version == 4
    with sqlite3.connect(path) as connection, sqlite3.connect(":memory:") as fresh:
        schema.init_game_write_schema(connection)
        schema.init_game_write_schema(fresh)
        assert schema.get_sns_public_namespace(connection) == namespace
        assert schema.get_sns_public_namespace(fresh) != namespace


def test_sqlite_backup_preserves_old_identity_but_new_branch_content_is_distinct() -> None:
    """データベース複製は既存参照を保ち、複製後に同じ整数で作った新規投稿は区別できる。"""
    with sqlite3.connect(":memory:") as original, sqlite3.connect(":memory:") as branch:
        original_posts = SqlitePostRepository.for_standalone_connection(original)
        old = original_posts.save(_post())
        original.backup(branch)
        branch_posts = SqlitePostRepository.for_standalone_connection(branch)
        assert schema.get_sns_public_namespace(original) == schema.get_sns_public_namespace(branch)
        assert branch_posts.find_by_id(old.post_id).identity_token == old.identity_token
        first, second = original_posts.save(_post(2)), branch_posts.save(_post(2))
        assert first.identity_token != second.identity_token


def test_legacy_rows_receive_stable_distinct_identity_during_migration() -> None:
    """旧形式の削除済み投稿も返信も一度だけ識別子を補完し、再初期化で発行し直さない。"""
    with sqlite3.connect(":memory:") as connection:
        apply_migrations(connection, namespace="game_write", migrations=schema._GAME_WRITE_MIGRATIONS[:35])
        connection.execute("INSERT INTO game_sns_posts VALUES (1, 1, '旧投稿', 'public', 1, '2026-01-01T00:00:00')")
        connection.execute("INSERT INTO game_sns_replies VALUES (1, 2, 1, NULL, '旧返信', 'public', 0, '2026-01-01T00:00:00')")
        connection.execute("INSERT INTO game_sns_users VALUES (1, 'hero', '勇者', '')")
        connection.commit()
        schema.init_game_write_schema(connection)
        tokens = [connection.execute(f"SELECT identity_token FROM {table}").fetchone()[0]
                  for table in ("game_sns_posts", "game_sns_replies", "game_sns_users")]
        assert len(set(tokens)) == 3
        assert all(UUID(hex=token).version == 4 for token in tokens)
        schema.init_game_write_schema(connection)
        assert tokens == [connection.execute(f"SELECT identity_token FROM {table}").fetchone()[0]
                          for table in ("game_sns_posts", "game_sns_replies", "game_sns_users")]
        assert not connection.in_transaction


@pytest.mark.parametrize("repository_type,create", [
    (SqlitePostRepository, _post), (SqliteReplyRepository, _reply),
])
def test_replacement_using_same_integer_does_not_inherit_deleted_identity(repository_type, create) -> None:
    """削除済み行の整数を再利用しても、置き換えた集約に過去の識別子を引き継がせない。"""
    with sqlite3.connect(":memory:") as connection:
        repository = repository_type.for_standalone_connection(connection)
        old = repository.save(create())
        repository.delete(old.content_id)
        replacement = repository.save(create())
        restored = repository.find_by_id(old.content_id)
        assert restored.identity_token == replacement.identity_token
        assert restored.identity_token != old.identity_token


@pytest.mark.parametrize("table,key,repository_type,create", [
    ("game_sns_posts", "post_id", SqlitePostRepository, _post),
    ("game_sns_replies", "reply_id", SqliteReplyRepository, _reply),
    ("game_sns_users", "user_id", SqliteSnsUserRepository, _user),
])
def test_identity_lookup_uses_unique_index(table, key, repository_type, create) -> None:
    """識別子からの検索は全走査にならず、同一種類の別行への識別子の重複も拒否する。"""
    with sqlite3.connect(":memory:") as connection:
        repository = repository_type.for_standalone_connection(connection)
        first, second = repository.save(create(1)), repository.save(create(2))
        plan = connection.execute(
            f"EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE identity_token = ?",
            (first.identity_token,),
        ).fetchall()
        assert any("SEARCH" in row[3] and "INDEX" in row[3] for row in plan)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"UPDATE {table} SET identity_token = ? WHERE {key} = ?",
                (first.identity_token, 2),
            )


def test_user_identity_survives_reopen_and_does_not_rebind_after_replacement(tmp_path) -> None:
    """利用者を開き直しても識別子は同じで、同じ整数と名前の別人に置き換えたときだけ変わる。"""
    path = tmp_path / "users.sqlite"
    user = _user()
    with sqlite3.connect(path) as connection:
        SqliteSnsUserRepository.for_standalone_connection(connection).save(user)
    with sqlite3.connect(path) as connection:
        repository = SqliteSnsUserRepository.for_standalone_connection(connection)
        assert repository.find_by_id(user.user_id).identity_token == user.identity_token
        repository.save(_user())
        assert repository.find_by_id(user.user_id).identity_token != user.identity_token


def test_missing_stored_identity_fails_without_issuing_a_new_one() -> None:
    """保存済み識別子や名前空間が欠けた場合、別の参照へ置換せず復元を拒否する。"""
    with sqlite3.connect(":memory:") as connection:
        repository = SqlitePostRepository.for_standalone_connection(connection)
        repository.save(_post())
        connection.execute("UPDATE game_sns_posts SET identity_token = NULL")
        with pytest.raises(SnsIdentityValidationException):
            repository.find_by_id(PostId(1))
        connection.execute("DELETE FROM game_sns_public_namespace")
        with pytest.raises(RuntimeError, match="名前空間"):
            schema.get_sns_public_namespace(connection)
        assert connection.execute("SELECT count(*) FROM game_sns_public_namespace").fetchone()[0] == 0


def test_identity_migration_does_not_commit_an_existing_transaction() -> None:
    """呼出側のトランザクション内では移行も一緒に巻き戻り、途中確定を起こさない。"""
    with sqlite3.connect(":memory:") as connection:
        apply_migrations(connection, namespace="game_write", migrations=schema._GAME_WRITE_MIGRATIONS[:35])
        connection.execute("BEGIN")
        schema.init_game_write_schema(connection)
        assert schema.get_sns_public_namespace(connection)
        connection.rollback()
        assert connection.execute("SELECT version FROM schema_migrations WHERE namespace = 'game_write'").fetchone()[0] == 35
        columns = connection.execute("PRAGMA table_info(game_sns_posts)").fetchall()
        assert "identity_token" not in {row[1] for row in columns}
