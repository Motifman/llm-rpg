"""作者と親の採番が再利用されても、既存 SNS の参照先は結び直されない。"""

import sqlite3
from uuid import uuid4

import pytest

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId
from ai_rpg_world.infrastructure.repository import game_write_sqlite_schema as schema
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.sqlite_migration import apply_migrations
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository


def _user() -> UserAggregate:
    return UserAggregate.create_new_user(UserId(1), "hero", "勇者", "")


def _post(user: UserAggregate) -> PostAggregate:
    return PostAggregate.create(
        PostId(1),
        user.user_id,
        PostContent("投稿"),
        author_identity_token=user.identity_token,
    )


def test_standard_samples_bind_authors_and_parents_at_creation() -> None:
    """標準サンプルも整数だけに頼らず、作成時の作者と親の識別子を保持する。"""
    store = InMemoryDataStore()
    for post in store.posts.values():
        assert post.author_identity_token == store.sns_users[post.author_user_id].identity_token
    for reply in store.replies.values():
        assert reply.author_identity_token == store.sns_users[reply.author_user_id].identity_token
        parent = store.posts[reply.parent_post_id] if reply.parent_post_id else store.replies[reply.parent_reply_id]
        assert reply.parent_identity_token == parent.identity_token


@pytest.mark.parametrize("nested", [False, True])
def test_sqlite_reference_tokens_survive_replacement_of_authors_and_parents(nested: bool) -> None:
    """作者と親が同じ整数の別対象に置換されても、保存済みの参照識別子は旧対象のままである。"""
    with sqlite3.connect(":memory:") as connection:
        users = SqliteSnsUserRepository.for_standalone_connection(connection)
        posts = SqlitePostRepository.for_standalone_connection(connection)
        replies = SqliteReplyRepository.for_standalone_connection(connection)
        author = users.save(_user())
        parent = posts.save(_post(author))
        first = replies.save(
            ReplyAggregate.create(
                ReplyId(1),
                parent.post_id,
                None,
                author.user_id,
                author.user_id,
                PostContent("返信"),
                author_identity_token=author.identity_token,
                parent_identity_token=parent.identity_token,
            )
        )
        target = first
        if nested:
            target = replies.save(
                ReplyAggregate.create(
                    ReplyId(2),
                    None,
                    first.reply_id,
                    author.user_id,
                    author.user_id,
                    PostContent("孫返信"),
                    author_identity_token=author.identity_token,
                    parent_identity_token=first.identity_token,
                )
            )
        stored_author, stored_parent = target.author_identity_token, target.parent_identity_token
        replacement_user = users.save(_user())
        posts.save(_post(replacement_user))
        if nested:
            replies.save(
                ReplyAggregate.create(
                    ReplyId(1),
                    PostId(1),
                    None,
                    replacement_user.user_id,
                    replacement_user.user_id,
                    PostContent("別返信"),
                    author_identity_token=replacement_user.identity_token,
                    parent_identity_token=posts.find_by_id(PostId(1)).identity_token,
                )
            )
        restored = replies.find_by_id(target.reply_id)
        assert restored.author_identity_token == stored_author
        assert restored.parent_identity_token == stored_parent
        assert restored.author_identity_token != replacement_user.identity_token
        current_parent = replies.find_by_id(ReplyId(1)) if nested else posts.find_by_id(PostId(1))
        assert restored.parent_identity_token != current_parent.identity_token
        replies.save(restored)
        assert replies.find_by_id(target.reply_id).parent_identity_token == stored_parent


def test_saved_missing_binding_does_not_attach_to_later_author() -> None:
    """作者の識別子が欠けた既存投稿は、後から同じ整数の利用者が現れても再結合しない。"""
    with sqlite3.connect(":memory:") as connection:
        posts = SqlitePostRepository.for_standalone_connection(connection)
        users = SqliteSnsUserRepository.for_standalone_connection(connection)
        old = posts.save(PostAggregate.create(PostId(1), UserId(1), PostContent("古い投稿")))
        users.save(_user())
        restored = posts.find_by_id(old.post_id)
        posts.save(restored)
        assert posts.find_by_id(old.post_id).author_identity_token is None


def test_post_author_binding_is_read_only() -> None:
    """保存先に関係なく、投稿の作者識別子を公開プロパティから置換できない。"""
    author = _user()
    post = _post(author)
    with pytest.raises(AttributeError):
        post.author_identity_token = _user().identity_token


def test_binding_migration_resolves_only_consistent_existing_references_once() -> None:
    """旧行の作者と唯一の親を一度だけ固定し、存在しない作者・親や二重親は未束縛のままにする。"""
    author_token, post_token, reply_token = uuid4().hex, uuid4().hex, uuid4().hex
    with sqlite3.connect(":memory:") as connection:
        apply_migrations(connection, namespace="game_write", migrations=schema._GAME_WRITE_MIGRATIONS[:36])
        connection.execute(
            "INSERT INTO game_sns_users VALUES (1, 'hero', '勇者', '', ?)",
            (author_token,),
        )
        for number, author in [(1, 1), (2, 999)]:
            connection.execute(
                "INSERT INTO game_sns_posts VALUES (?, ?, '投稿', 'public', 0, '2026-01-01T00:00:00', ?)",
                (number, author, post_token if number == 1 else uuid4().hex),
            )
        for number, parent_post, parent_reply in [(1, 1, None), (2, None, 1), (3, 1, 1), (4, 999, None)]:
            connection.execute(
                "INSERT INTO game_sns_replies VALUES (?, 1, ?, ?, '返信', 'public', 0, '2026-01-01T00:00:00', ?)",
                (number, parent_post, parent_reply, reply_token if number == 1 else uuid4().hex),
            )
        connection.commit()
        schema.init_game_write_schema(connection)
        assert connection.execute("SELECT author_identity_token FROM game_sns_posts ORDER BY post_id").fetchall() == [
            (author_token,),
            (None,),
        ]
        assert connection.execute(
            "SELECT parent_identity_token FROM game_sns_replies ORDER BY reply_id"
        ).fetchall() == [(post_token,), (reply_token,), (None,), (None,)]
        connection.execute("UPDATE game_sns_users SET identity_token = ?", (uuid4().hex,))
        connection.execute("UPDATE game_sns_posts SET identity_token = ? WHERE post_id = 1", (uuid4().hex,))
        schema.init_game_write_schema(connection)
        assert (
            connection.execute("SELECT author_identity_token FROM game_sns_posts WHERE post_id = 1").fetchone()[0]
            == author_token
        )
        assert (
            connection.execute("SELECT parent_identity_token FROM game_sns_replies WHERE reply_id = 1").fetchone()[0]
            == post_token
        )
