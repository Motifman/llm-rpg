"""公開SNSの候補取得は、関連集合を復元せず同じ件数上限で継続できる。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility
from ai_rpg_world.domain.sns.exception.identity_token_exception import SnsIdentityValidationException
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import init_game_write_schema
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from ai_rpg_world.infrastructure.repository.in_memory_public_sns_read_repository import InMemoryPublicSnsReadRepository
from ai_rpg_world.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_notification_repository import (
    InMemorySnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_public_sns_read_repository import SqlitePublicSnsReadRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import SqliteSnsNotificationRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository


@dataclass
class _Backend:
    reader: Any
    posts: Any
    replies: Any
    notifications: Any
    connection: sqlite3.Connection | None = None
    store: InMemoryDataStore | None = None


@pytest.fixture(params=["memory", "sqlite"])
def backend(request):
    if request.param == "memory":
        store = InMemoryDataStore()
        store.posts.clear()
        store.replies.clear()
        store.sns_notifications.clear()
        yield _Backend(
            InMemoryPublicSnsReadRepository(store),
            InMemoryPostRepository(store),
            InMemoryReplyRepository(store),
            InMemorySnsNotificationRepository(store),
            store=store,
        )
    else:
        with sqlite3.connect(":memory:") as connection:
            init_game_write_schema(connection)
            yield _Backend(
                SqlitePublicSnsReadRepository(connection),
                SqlitePostRepository.for_standalone_connection(connection),
                SqliteReplyRepository.for_standalone_connection(connection),
                SqliteSnsNotificationRepository.for_standalone_connection(connection),
                connection=connection,
            )


def _post(
    number: int, *, private: bool = False, deleted: bool = False, identity_token: str | None = None,
) -> PostAggregate:
    return PostAggregate.create_from_db(
        PostId(number), UserId(1),
        PostContent("投稿", visibility=PostVisibility.PRIVATE if private else PostVisibility.PUBLIC),
        set(), set(), set(), deleted=deleted,
        created_at=datetime(2026, 1, 1) - timedelta(seconds=number),
        identity_token=identity_token,
        author_identity_token="11111111111141118111111111111111",
    )


def _reply(
    number: int, *, post: int | None = None, reply: int | None = None, identity_token: str | None = None,
) -> ReplyAggregate:
    return ReplyAggregate.create_from_db(
        ReplyId(number), None if post is None else PostId(post),
        None if reply is None else ReplyId(reply), UserId(2),
        PostContent("返信"), set(), set(), set(), created_at=datetime(2026, 1, 1),
        identity_token=identity_token,
        author_identity_token="22222222222242228222222222222222",
        parent_identity_token="33333333333343338333333333333333",
    )


def _notification(number: int, owner: int) -> Notification:
    return Notification.create_persistent_notification(
        NotificationId(number), UserId(owner), NotificationType.FOLLOW,
        NotificationContent.create_follow_notification(UserId(2), "魔法使い"),
        created_at=datetime(2026, 1, 1) - timedelta(seconds=number),
    )


def test_posts_use_exclusive_id_cursor_without_filtering_candidates(backend) -> None:
    """候補は作成日時や閲覧可否に関係なく整数IDの降順で返し、次のページは境界を除外する。"""
    for post in [_post(1), _post(2, private=True), _post(3, deleted=True), _post(4)]:
        backend.posts.save(post)
    first = backend.reader.scan_posts(None, 2)
    second = backend.reader.scan_posts(first[-1].local_id, 2)
    assert [row.local_id for row in first] == [4, 3]
    assert [row.local_id for row in second] == [2, 1]
    assert first[-1].deleted
    assert second[0].visibility is PostVisibility.PRIVATE
    assert backend.reader.scan_posts(1, 2) == []


def test_replies_return_only_immediate_children_with_exclusive_cursor(backend) -> None:
    """親投稿と親返信の同じ整数を混同せず、孫を直接の返信一覧へ混ぜない。"""
    for reply in [_reply(1, post=1), _reply(2, post=1), _reply(3, reply=1), _reply(4, reply=3)]:
        backend.replies.save(reply)
    assert [row.local_id for row in backend.reader.scan_replies("post", 1, None, 1)] == [2]
    assert [row.local_id for row in backend.reader.scan_replies("post", 1, 2, 2)] == [1]
    child = backend.reader.scan_replies("reply", 1, None, 2)
    assert [row.local_id for row in child] == [3]
    assert (child[0].parent_kind, child[0].parent_id) == ("reply", 1)


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_identity_lookup_and_integer_lookup_return_the_same_scalar_record(backend, kind) -> None:
    """投稿と返信は不変識別子と内部整数のどちらで照会しても同じ小さい読取結果を返す。"""
    aggregate = _post(1) if kind == "post" else _reply(1, post=1)
    writer = backend.posts if kind == "post" else backend.replies
    writer.save(aggregate)
    found = backend.reader.find_content(kind, aggregate.identity_token)
    assert found == backend.reader.find_content_by_id(kind, 1)
    assert found.identity_token == aggregate.identity_token
    assert found.kind == kind
    assert found.author_user_id == int(aggregate.author_user_id)
    assert found.content == aggregate.content.content
    assert found.author_identity_token == aggregate.author_identity_token
    assert found.parent_identity_token == (aggregate.parent_identity_token if kind == "reply" else None)
    assert not hasattr(found, "likes")
    assert not hasattr(found, "reply_ids")
    assert backend.reader.find_content(kind, "0" * 32) is None
    assert backend.reader.find_content_by_id(kind, 999) is None


def test_notification_pages_filter_owner_before_limiting_and_do_not_mark_read(backend) -> None:
    """通知は本人分を先に絞って整数ID降順で区切り、取得や取得結果の変更では既読にしない。"""
    for number, owner in [(1, 1), (2, 2), (3, 1), (4, 2), (5, 1)]:
        backend.notifications.save(_notification(number, owner))
    first = backend.reader.scan_notifications(1, None, 2)
    second = backend.reader.scan_notifications(1, 3, 2)
    assert [int(item.notification_id) for item in first] == [5, 3]
    assert [int(item.notification_id) for item in second] == [1]
    assert all(item.user_id == UserId(1) for item in [*first, *second])
    first[0].mark_as_read()
    assert not backend.notifications.find_by_id(NotificationId(5)).is_read


@pytest.mark.parametrize("limit", [0, -1, 102, True, 1.5])
@pytest.mark.parametrize("method,args", [
    ("scan_posts", (None,)),
    ("scan_replies", ("post", 1, None)),
    ("scan_notifications", (1, None)),
])
def test_all_scan_methods_reject_limits_outside_bounded_integer_range(backend, method, args, limit) -> None:
    """候補取得の上限は1から101までの整数だけを受け付け、真偽値も拒否する。"""
    with pytest.raises(ValueError):
        getattr(backend.reader, method)(*args, limit)


def test_upper_bound_returns_no_more_than_101_records(backend, monkeypatch) -> None:
    """最大件数を要求しても102件以上の候補を復元しない。"""
    for number in range(1, 105):
        backend.posts.save(_post(number))
    restored: list[int] = []
    original = backend.reader._record

    def count_record(kind, source):
        record = original(kind, source)
        restored.append(record.local_id)
        return record

    monkeypatch.setattr(backend.reader, "_record", count_record)
    page = backend.reader.scan_posts(None, 101)
    assert len(restored) == 101
    assert len(page) == 101
    assert [page[0].local_id, page[-1].local_id] == [104, 4]


def test_sqlite_content_reads_do_not_touch_like_mention_or_child_collections() -> None:
    """SQLiteの本文取得は関連集合を問い合わせず、継続取得にWHERE・ORDER BY・LIMITを使う。"""
    with sqlite3.connect(":memory:") as connection:
        init_game_write_schema(connection)
        reader = SqlitePublicSnsReadRepository(connection)
        post = _post(1)
        SqlitePostRepository.for_standalone_connection(connection).save(post)
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        reader.find_content("post", post.identity_token)
        reader.find_content_by_id("post", 1)
        reader.scan_posts(2, 1)
        assert len(statements) == 3
        assert all("game_sns_posts" in query for query in statements)
        assert all("identity_token" in query for query in statements)
        assert all("SELECT *" not in query.upper() for query in statements)
        assert "WHERE post_id < 2" in statements[-1]
        assert "ORDER BY post_id DESC LIMIT 1" in statements[-1]


def test_memory_content_reads_never_copy_or_inspect_related_collections(monkeypatch) -> None:
    """メモリー上でも投稿のいいね・返信一覧を開かず、必要な本文だけを読む。"""
    store = InMemoryDataStore()
    store.posts.clear()
    post = _post(1)
    store.posts[post.post_id] = post
    reader = InMemoryPublicSnsReadRepository(store)

    def fail_collection_access(_self):
        raise AssertionError("関連集合を参照した")

    monkeypatch.setattr(PostAggregate, "likes", property(fail_collection_access))
    monkeypatch.setattr(PostAggregate, "reply_ids", property(fail_collection_access))
    assert reader.scan_posts(None, 1)[0].content == "投稿"
    assert reader.find_content("post", post.identity_token).content == "投稿"
    assert reader.find_content_by_id("post", 1).content == "投稿"


def test_sqlite_reader_construction_does_not_initialize_schema() -> None:
    """読取アダプターを作るだけでは、移行やコミットを含むSQLを実行しない。"""
    with sqlite3.connect(":memory:") as connection:
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        SqlitePublicSnsReadRepository(connection)
        assert statements == []


def test_sqlite_namespace_lookup_keeps_active_transaction_open() -> None:
    """名前空間の参照はSELECTだけで、呼出し元の書込トランザクションを確定しない。"""
    with sqlite3.connect(":memory:") as connection:
        init_game_write_schema(connection)
        connection.execute("BEGIN")
        reader = SqlitePublicSnsReadRepository(connection)
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        assert reader.namespace == reader.namespace
        assert connection.in_transaction
        assert len(statements) == 2
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def test_user_lookup_is_scalar_and_block_lookup_checks_only_the_requested_pair(backend) -> None:
    """利用者を小さい読取結果にし、ブロックの有無は利用者の組を指定して確認する。"""
    user = UserAggregate.create_new_user(UserId(7), "test_user", "試験利用者", "")
    user.follow(UserId(8))
    user.block(UserId(9))
    if backend.store is not None:
        backend.store.sns_users[user.user_id] = user
    else:
        SqliteSnsUserRepository.for_standalone_connection(backend.connection).save(user)
    found = backend.reader.find_user(7)
    assert found.identity_token == user.identity_token
    assert found.user_id == 7
    assert found.display_name == "試験利用者"
    assert not hasattr(found, "follow_relationships")
    assert not hasattr(found, "block_relationships")
    assert backend.reader.has_block(7, 9)
    assert not backend.reader.has_block(9, 7)
    assert not backend.reader.has_block(7, 8)
    assert not backend.reader.has_block(999, 7)
    assert backend.reader.find_user(999) is None


@pytest.mark.parametrize("parent_post_id,parent_reply_id", [(1, 2), (None, None)])
def test_sqlite_malformed_reply_parent_does_not_choose_a_convenient_ancestor(
    parent_post_id, parent_reply_id,
) -> None:
    """親が二つある返信や親がない返信は、どちらかの親を勝手に選んで読取結果へ載せない。"""
    with sqlite3.connect(":memory:") as connection:
        writer = SqliteReplyRepository.for_standalone_connection(connection)
        reply = writer.save(_reply(1, post=1))
        connection.execute(
            "UPDATE game_sns_replies SET parent_post_id = ?, parent_reply_id = ? WHERE reply_id = 1",
            (parent_post_id, parent_reply_id),
        )
        record = SqlitePublicSnsReadRepository(connection).find_content("reply", reply.identity_token)
        assert record.parent_kind is None
        assert record.parent_id is None
        assert record.parent_identity_token == reply.parent_identity_token


def test_sqlite_user_lookup_does_not_load_relationship_collections() -> None:
    """SQLiteの利用者参照は関係集合を復元せず、ブロック確認も一組を上限1件で読む。"""
    with sqlite3.connect(":memory:") as connection:
        user = UserAggregate.create_new_user(UserId(1), "test_user", "試験利用者", "")
        SqliteSnsUserRepository.for_standalone_connection(connection).save(user)
        reader = SqlitePublicSnsReadRepository(connection)
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        assert reader.find_user(1).display_name == "試験利用者"
        assert not reader.has_block(1, 2)
        assert len(statements) == 2
        assert "SELECT user_id, identity_token, display_name" in statements[0]
        assert "blocker_user_id = 1 AND blocked_user_id = 2" in statements[1]
        assert all(query.endswith("LIMIT 1") for query in statements)


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_memory_duplicate_identity_is_rejected_instead_of_selecting_first_match(kind) -> None:
    """異常な手動取込で識別子が重複しても、先に入った別対象を返さない。"""
    store = InMemoryDataStore()
    store.posts.clear()
    store.replies.clear()
    if kind == "post":
        first = _post(1)
        second = _post(2, identity_token=first.identity_token)
        store.posts.update({first.post_id: first, second.post_id: second})
    else:
        first = _reply(1, post=1)
        second = _reply(2, post=1, identity_token=first.identity_token)
        store.replies.update({first.reply_id: first, second.reply_id: second})
    reader = InMemoryPublicSnsReadRepository(store)
    assert reader.find_content(kind, first.identity_token) is None


@pytest.mark.parametrize("identity_token", [
    None, "invalid", "11111111-1111-4111-8111-111111111111", "ABCDEFAB123441238123ABCDEFABCDEF",
])
@pytest.mark.parametrize("kind", ["post", "reply"])
@pytest.mark.parametrize("read_method", ["by_id", "scan"])
def test_sqlite_content_reads_reject_missing_or_noncanonical_stored_identity(
    identity_token, kind, read_method,
) -> None:
    """保存済み識別子がNULL・不正値・非正規形なら、文字列化や再発行せず復元を拒否する。"""
    with sqlite3.connect(":memory:") as connection:
        if kind == "post":
            SqlitePostRepository.for_standalone_connection(connection).save(_post(1))
        else:
            SqliteReplyRepository.for_standalone_connection(connection).save(_reply(1, post=1))
        table = "game_sns_posts" if kind == "post" else "game_sns_replies"
        connection.execute(f"UPDATE {table} SET identity_token = ?", (identity_token,))
        reader = SqlitePublicSnsReadRepository(connection)
        with pytest.raises(SnsIdentityValidationException):
            if read_method == "by_id":
                reader.find_content_by_id(kind, 1)
            elif kind == "post":
                reader.scan_posts(None, 1)
            else:
                reader.scan_replies("post", 1, None, 1)


@pytest.mark.parametrize("identity_token", [
    None, "invalid", "11111111-1111-4111-8111-111111111111", "ABCDEFAB123441238123ABCDEFABCDEF",
])
def test_sqlite_user_read_rejects_missing_or_noncanonical_stored_identity(identity_token) -> None:
    """利用者の薄い読取でも保存済み識別子を検証し、破損を明示する例外で停止する。"""
    with sqlite3.connect(":memory:") as connection:
        user = UserAggregate.create_new_user(UserId(1), "test_user", "試験利用者", "")
        SqliteSnsUserRepository.for_standalone_connection(connection).save(user)
        connection.execute("UPDATE game_sns_users SET identity_token = ?", (identity_token,))
        with pytest.raises(SnsIdentityValidationException):
            SqlitePublicSnsReadRepository(connection).find_user(1)


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_sqlite_token_lookup_rejects_malformed_stored_identity(kind) -> None:
    """不正な保存済み識別子が照会値と一致しても、本文を返す前に破損を検出する。"""
    with sqlite3.connect(":memory:") as connection:
        if kind == "post":
            SqlitePostRepository.for_standalone_connection(connection).save(_post(1))
        else:
            SqliteReplyRepository.for_standalone_connection(connection).save(_reply(1, post=1))
        table = "game_sns_posts" if kind == "post" else "game_sns_replies"
        connection.execute(f"UPDATE {table} SET identity_token = 'invalid'")
        with pytest.raises(SnsIdentityValidationException):
            SqlitePublicSnsReadRepository(connection).find_content(kind, "invalid")


@pytest.mark.parametrize("identity_token", [None, "invalid"])
@pytest.mark.parametrize("kind", ["post", "reply", "user"])
def test_memory_scalar_reads_reject_corrupted_identity(identity_token, kind) -> None:
    """メモリー内の保存状態が破損した場合も、利用者・投稿・返信の無効な識別子を出力しない。"""
    store = InMemoryDataStore()
    store.posts.clear()
    store.replies.clear()
    if kind == "post":
        aggregate = _post(1)
        store.posts[aggregate.post_id] = aggregate
    elif kind == "reply":
        aggregate = _reply(1, post=1)
        store.replies[aggregate.reply_id] = aggregate
    else:
        aggregate = store.sns_users[UserId(1)]
    object.__setattr__(aggregate._identity_token, "value", identity_token)
    reader = InMemoryPublicSnsReadRepository(store)
    with pytest.raises(SnsIdentityValidationException):
        if kind == "user":
            reader.find_user(1)
        else:
            reader.find_content_by_id(kind, 1)


@pytest.mark.parametrize("namespace", [
    "invalid", "11111111-1111-4111-8111-111111111111", "ABCDEFAB123441238123ABCDEFABCDEF",
])
def test_namespace_read_rejects_noncanonical_stored_value(backend, namespace) -> None:
    """保存済み名前空間が正規形のUUID4でなければ、無効な公開参照を生成する前に停止する。"""
    if backend.store is not None:
        backend.store.sns_public_namespace = namespace
    else:
        backend.connection.execute("UPDATE game_sns_public_namespace SET namespace = ?", (namespace,))
    with pytest.raises(SnsIdentityValidationException):
        _ = backend.reader.namespace


def test_memory_namespace_read_rejects_missing_value() -> None:
    """メモリーの名前空間が欠損しても、読み取り時に別の名前空間を発行しない。"""
    store = InMemoryDataStore()
    store.sns_public_namespace = None
    with pytest.raises(SnsIdentityValidationException):
        _ = InMemoryPublicSnsReadRepository(store).namespace
