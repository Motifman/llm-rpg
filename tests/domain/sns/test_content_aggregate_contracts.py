"""投稿と返信の公開操作で、元の入力・状態遷移・未発行イベントを保持する。"""

from copy import deepcopy
from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.aggregate import PostAggregate, ReplyAggregate
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.event import (
    SnsContentDeletedEvent,
    SnsContentLikedEvent,
    SnsContentMentionedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
)
from ai_rpg_world.domain.sns.exception import (
    ContentAlreadyDeletedException,
    InvalidContentTypeException,
    InvalidParentReferenceException,
    OwnershipException,
)
from ai_rpg_world.domain.sns.value_object import Like, Mention, PostContent, PostId, ReplyId, UserId

SAVED_AT = datetime(2020, 2, 3, 4, 5, 6)
LIKED_AT = datetime(2020, 2, 4, 5, 6, 7)
TARGET_TOKEN = "00000000000040008000000000000011"
AUTHOR_TOKEN = "00000000000040008000000000000022"
PARENT_TOKEN = "00000000000040008000000000000033"
ACTOR_TOKEN = "00000000000040008000000000000044"


def _create(kind, content=None, *, number=1, parent_post=1, parent_reply=None):
    if content is None:
        content = PostContent("テスト投稿" if kind == "post" else "テスト返信")
    if kind == "post":
        return PostAggregate.create(PostId(number), UserId(1), content)
    return ReplyAggregate.create(
        ReplyId(number),
        None if parent_post is None else PostId(parent_post),
        None if parent_reply is None else ReplyId(parent_reply),
        UserId(2),
        UserId(1),
        content,
    )


def _like(aggregate, user):
    if isinstance(aggregate, PostAggregate):
        aggregate.like_post(user)
    else:
        aggregate.like_reply(user)


def _delete(aggregate, user):
    if isinstance(aggregate, PostAggregate):
        aggregate.delete_post(user)
    else:
        aggregate.delete_reply(user)


def _state(aggregate):
    """可変集合の参照を共有せず、公開状態を値へ写す。"""
    return (
        aggregate.content_id,
        aggregate.author_user_id,
        aggregate.content.content,
        tuple(aggregate.content.hashtags),
        aggregate.content.visibility,
        frozenset((like.user_id, like.post_id, like.created_at) for like in aggregate.likes),
        frozenset((mention.mentioned_user_name, mention.post_id) for mention in aggregate.mentions),
        frozenset(aggregate.reply_ids),
        aggregate.deleted,
        aggregate.parent_post_id,
        aggregate.parent_reply_id,
        aggregate.created_at,
        aggregate.identity_token,
        aggregate.author_identity_token,
        aggregate.parent_identity_token,
    )


def _events(aggregate):
    # 作成イベントのmentions、likeのprovenanceもbeforeと参照を共有させない。
    return deepcopy(tuple(aggregate.get_events()))


def _assert_like_event(event, aggregate, user, content_type, liked):
    assert type(event) is SnsContentLikedEvent
    assert event.aggregate_id == aggregate.content_id
    assert event.aggregate_type == ("PostAggregate" if isinstance(aggregate, PostAggregate) else "ReplyAggregate")
    assert event.target_id == aggregate.content_id
    assert event.user_id == user
    assert event.content_author_id == UserId(1)
    assert event.content_type == content_type
    assert event.content_text == aggregate.content.content
    assert event.is_liked is liked


@pytest.mark.parametrize(
    ("kind", "number", "parent_post", "parent_reply", "body", "names"),
    [
        ("post", 1, None, None, "テスト投稿", set()),
        ("reply", 1, 1, None, "テスト返信", set()),
        ("reply", 1, None, 2, "テスト返信", set()),
        ("reply", 2, None, 1, "テスト返信", set()),
        ("post", 1, None, None, "@user1 @user2 テスト投稿", {"user1", "user2"}),
        ("reply", 1, 1, None, "@user1 @user2 テスト返信", {"user1", "user2"}),
        ("post", 1, None, None, "@user1 @user2 こんにちは #test", {"user1", "user2"}),
        ("post", 1, None, None, "メンションなしの投稿 #test", set()),
        ("post", 1, None, None, "@user1 @user2 テスト投稿 #hashtag", {"user1", "user2"}),
        ("post", 1, None, None, "メンションなしの投稿 #hashtag", set()),
        ("post", 1, None, None, "@@user1 テスト", {"@user1"}),
        ("post", 1, None, None, "@user1! テスト", {"user1!"}),
        ("post", 1, None, None, "@user1   @user2", {"user1", "user2"}),
        ("reply", 1, 1, None, "@user1 @user2 こんにちは！ #test", {"user1", "user2"}),
        ("reply", 1, 1, None, "メンションなしの返信", set()),
        ("reply", 1, 1, None, "@user_name @user-name @user.name テスト", {"user_name", "user-name", "user.name"}),
        ("post", 1, None, None, "@user1 テスト投稿", {"user1"}),
        ("reply", 1, 1, None, "@user1 テスト返信", {"user1"}),
    ],
)
def test_creation_preserves_fields_mentions_and_ordered_events(kind, number, parent_post, parent_reply, body, names):
    """元の本文と型付きID・親を保持し、作成の後に必要なメンションだけを一度発行する。"""
    content = PostContent(body)
    aggregate = _create(kind, content, number=number, parent_post=parent_post, parent_reply=parent_reply)
    content_id = PostId(number) if kind == "post" else ReplyId(number)
    expected_parent = (
        None if parent_post is None else PostId(parent_post),
        None if parent_reply is None else ReplyId(parent_reply),
    )
    assert aggregate.content_id == content_id
    assert aggregate.author_user_id == UserId(1)
    assert aggregate.content == content
    assert aggregate.content.content == body
    assert aggregate.likes == set()
    assert aggregate.mentions == {Mention(name, content_id) for name in names}
    assert aggregate.get_mentioned_users() == names
    assert aggregate.deleted is False
    assert (aggregate.parent_post_id, aggregate.parent_reply_id) == expected_parent
    assert aggregate.get_parent_info() == expected_parent
    assert aggregate.get_content_type() == kind
    if kind == "post":
        assert aggregate.post_id == PostId(number)
        assert aggregate.post_content == content
        assert aggregate.mentioned_users() == names
    else:
        assert aggregate.reply_id == ReplyId(number)
    events = aggregate.get_events()
    assert len(events) == (2 if names else 1)
    creation = events[0]
    assert type(creation) is (SnsPostCreatedEvent if kind == "post" else SnsReplyCreatedEvent)
    assert creation.aggregate_id == content_id
    assert creation.aggregate_type == ("PostAggregate" if kind == "post" else "ReplyAggregate")
    assert creation.author_user_id == UserId(1)
    assert creation.content == content
    assert creation.mentions == {Mention(name, content_id) for name in names}
    if kind == "post":
        assert creation.post_id == PostId(number)
    else:
        assert creation.reply_id == ReplyId(number)
        assert (creation.parent_post_id, creation.parent_reply_id) == expected_parent
        assert creation.parent_author_id == UserId(2)
    if names:
        mention = events[1]
        assert type(mention) is SnsContentMentionedEvent
        assert mention.aggregate_id == content_id
        assert mention.aggregate_type == creation.aggregate_type
        assert mention.target_id == content_id
        assert mention.mentioned_by_user_id == UserId(1)
        assert mention.mentioned_user_names == names
        assert mention.content_type == kind


@pytest.mark.parametrize(
    ("kind", "parent_post", "parent_reply"), [("post", None, None), ("reply", 1, None), ("reply", None, 2)]
)
def test_constructor_preserves_supplied_state(kind, parent_post, parent_reply):
    """直接構築でも、元の空集合・作者・本文と投稿親または返信親を保持する。"""
    content = PostContent("テスト投稿" if kind == "post" else "テスト返信")
    if kind == "post":
        aggregate = PostAggregate(PostId(1), UserId(1), content, set(), set(), set())
    else:
        aggregate = ReplyAggregate(
            ReplyId(1),
            UserId(1),
            content,
            set(),
            set(),
            set(),
            deleted=False,
            parent_post_id=None if parent_post is None else PostId(parent_post),
            parent_reply_id=None if parent_reply is None else ReplyId(parent_reply),
        )
    assert aggregate.content_id == (PostId(1) if kind == "post" else ReplyId(1))
    assert aggregate.author_user_id == UserId(1)
    assert aggregate.content == content
    assert aggregate.likes == set()
    assert aggregate.mentions == set()
    assert aggregate.deleted is False
    assert aggregate.parent_post_id == (None if parent_post is None else PostId(parent_post))
    assert aggregate.parent_reply_id == (None if parent_reply is None else ReplyId(parent_reply))
    assert aggregate.get_events() == []


@pytest.mark.parametrize(
    ("kind", "populated", "legacy_target", "saved", "nested"),
    [
        ("post", False, False, False, False),
        ("reply", False, False, False, False),
        ("post", True, False, False, False),
        ("reply", True, True, False, False),
        ("post", True, False, True, False),
        ("reply", True, False, True, False),
        ("reply", True, False, True, True),
    ],
    ids=[
        "post-empty",
        "reply-empty",
        "post-original",
        "reply-original-post-id",
        "post-saved",
        "reply-saved-post-parent",
        "reply-saved-reply-parent",
    ],
)
def test_restore_preserves_saved_state_without_events(kind, populated, legacy_target, saved, nested):
    """空集合と旧混在IDを含む元復元入力を保ち、保存時刻・各識別子を再発行せず復元する。"""
    content_id = PostId(1) if kind == "post" else ReplyId(1)
    target = PostId(1) if legacy_target else content_id
    content = PostContent("テスト投稿" if kind == "post" else "テスト返信")
    likes = ({Like(UserId(2), target, LIKED_AT)} if saved else {Like(UserId(2), target)}) if populated else set()
    mentions = {Mention("user1", target)} if populated else set()
    children = {ReplyId(8), ReplyId(9)} if saved else set()
    extra = dict(created_at=SAVED_AT, identity_token=TARGET_TOKEN, author_identity_token=AUTHOR_TOKEN) if saved else {}
    if kind == "post":
        aggregate = PostAggregate.create_from_db(
            PostId(1), UserId(1), content, likes, mentions, children, saved, **extra
        )
    else:
        aggregate = ReplyAggregate.create_from_db(
            ReplyId(1),
            None if nested else PostId(1),
            ReplyId(2) if nested else None,
            UserId(1),
            content,
            likes,
            mentions,
            children,
            saved,
            **extra,
            **({"parent_identity_token": PARENT_TOKEN} if saved else {}),
        )
    assert aggregate.content_id == content_id
    assert aggregate.author_user_id == UserId(1)
    assert aggregate.content == content
    assert aggregate.likes == likes
    assert aggregate.mentions == mentions
    assert aggregate.reply_ids == children
    assert aggregate.deleted is saved
    assert aggregate.parent_post_id == (PostId(1) if kind == "reply" and not nested else None)
    assert aggregate.parent_reply_id == (ReplyId(2) if nested else None)
    assert aggregate.get_events() == []
    if saved:
        assert aggregate.created_at == SAVED_AT
        assert aggregate.identity_token == TARGET_TOKEN
        assert aggregate.author_identity_token == AUTHOR_TOKEN
        assert aggregate.parent_identity_token == (PARENT_TOKEN if kind == "reply" else None)
        assert {(like.user_id, like.post_id, like.created_at) for like in aggregate.likes} == {
            (UserId(2), content_id, LIKED_AT)
        }


@pytest.mark.parametrize(
    ("attribute", "addition"), [("likes", "dummy"), ("mentions", "dummy"), ("reply_ids", ReplyId(1))]
)
def test_collection_getters_do_not_expose_owned_state(attribute, addition):
    """空の返却集合へ元のdummyまたは返信IDを加えても、投稿の内部状態は変わらない。"""
    post = _create("post")
    before = _state(post), _events(post)
    returned = getattr(post, attribute)
    returned.add(addition)
    assert getattr(post, attribute) == set()
    assert (_state(post), _events(post)) == before


@pytest.mark.parametrize(
    ("kind", "body", "initial_count"),
    [("post", "テスト投稿", 1), ("reply", "テスト返信", 1), ("post", "@testuser テスト投稿", 2)],
)
def test_like_toggle_preserves_actor_state_and_event_prefix(kind, body, initial_count):
    """同じ利用者の追加と解除で1→0となり、元の1件または2件のイベント列を残して各1件追加する。"""
    aggregate = _create(kind, PostContent(body))
    prefix = _events(aggregate)
    assert len(prefix) == initial_count
    assert type(prefix[0]) is (SnsPostCreatedEvent if kind == "post" else SnsReplyCreatedEvent)
    if initial_count == 2:
        assert type(prefix[1]) is SnsContentMentionedEvent
        assert prefix[1].mentioned_user_names == {"testuser"}
    for index, expected in enumerate((True, False), 1):
        _like(aggregate, UserId(2))
        assert aggregate.is_liked_by_user(UserId(2)) is expected
        assert len(aggregate.likes) == (1 if expected else 0)
        assert (Like(UserId(2), aggregate.content_id) in aggregate.likes) is expected
        events = aggregate.get_events()
        assert len(events) == initial_count + index
        assert tuple(events[:-1]) == prefix
        _assert_like_event(events[-1], aggregate, UserId(2), kind, expected)
        prefix = _events(aggregate)


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_like_toggle_preserves_other_users(kind):
    """利用者2・3・4がいいねした後3だけ解除すると、2と4のいいねが残る。"""
    aggregate = _create(kind)
    for user in (2, 3, 4):
        _like(aggregate, UserId(user))
    assert len(aggregate.likes) == 3
    assert all(aggregate.is_liked_by_user(UserId(user)) for user in (2, 3, 4))
    _like(aggregate, UserId(3))
    assert aggregate.is_liked_by_user(UserId(3)) is False
    assert len(aggregate.likes) == 2
    assert {like.user_id for like in aggregate.likes} == {UserId(2), UserId(4)}


def test_post_workflow_keeps_every_intermediate_state():
    """元のメンション投稿で2人のいいね、1人の解除、作者削除の全途中状態を保つ。"""
    post = _create("post", PostContent("@user1 @user2 テスト投稿"))
    assert post.deleted is False
    assert post.likes == set()
    assert post.get_mentioned_users() == {"user1", "user2"}
    post.like_post(UserId(2))
    post.like_post(UserId(3))
    assert len(post.likes) == 2
    assert post.is_liked_by_user(UserId(2)) is True
    assert post.is_liked_by_user(UserId(3)) is True
    post.like_post(UserId(2))
    assert post.is_liked_by_user(UserId(2)) is False
    assert len(post.likes) == 1
    post.delete_post(UserId(1))
    assert post.deleted is True
    assert {like.user_id for like in post.likes} == {UserId(3)}
    assert post.get_mentioned_users() == {"user1", "user2"}


@pytest.mark.parametrize(("kind", "with_like"), [("post", False), ("reply", False), ("post", True)])
def test_delete_preserves_existing_state_and_event_prefix(kind, with_like):
    """作者の削除はdeletedだけを変え、元のいいねと未発行イベントを残して削除を1件追加する。"""
    aggregate = _create(kind)
    if with_like:
        _like(aggregate, UserId(2))
        assert len(aggregate.likes) == 1
    likes = frozenset(aggregate.likes)
    prefix = _events(aggregate)
    assert len(prefix) == (2 if with_like else 1)
    _delete(aggregate, UserId(1))
    assert aggregate.deleted is True
    assert frozenset(aggregate.likes) == likes
    if with_like:
        assert aggregate.is_liked_by_user(UserId(2)) is True
    events = aggregate.get_events()
    assert len(events) == len(prefix) + 1
    assert tuple(events[:-1]) == prefix
    event = events[-1]
    assert type(event) is SnsContentDeletedEvent
    assert event.aggregate_id == aggregate.content_id
    assert event.aggregate_type == ("PostAggregate" if kind == "post" else "ReplyAggregate")
    assert event.target_id == aggregate.content_id
    assert event.author_user_id == UserId(1)
    assert event.content_type == kind


@pytest.mark.parametrize(
    ("kind", "operation", "actor", "content_type", "already_deleted", "exception", "message"),
    [
        (
            "post",
            "like",
            2,
            "invalid_type",
            False,
            InvalidContentTypeException,
            "コンテンツタイプは「post」または「reply」である必要があります",
        ),
        (
            "post",
            "delete",
            1,
            "invalid_type",
            False,
            InvalidContentTypeException,
            "コンテンツタイプは「post」または「reply」である必要があります",
        ),
        (
            "reply",
            "delete",
            1,
            "invalid_type",
            False,
            InvalidContentTypeException,
            "コンテンツタイプは「post」または「reply」である必要があります",
        ),
        ("post", "delete", 2, "post", False, OwnershipException, "ユーザーはこのpostを削除する権限がありません"),
        ("reply", "delete", 2, "reply", False, OwnershipException, "ユーザーはこのreplyを削除する権限がありません"),
        ("post", "delete", 1, "post", True, ContentAlreadyDeletedException, "すでに削除済みのpostは削除できません"),
        ("reply", "delete", 1, "reply", True, ContentAlreadyDeletedException, "すでに削除済みのreplyは削除できません"),
    ],
)
def test_rejected_content_operation_preserves_state_and_events(
    kind, operation, actor, content_type, already_deleted, exception, message
):
    """正しい拒否ガードへ到達し、非空の別対象・子返信・メンション・既存イベントを変更しない。"""
    aggregate = _create(kind)
    _like(aggregate, UserId(4))
    aggregate.add_mention(Mention("unrelated", aggregate.content_id))
    aggregate.add_reply(ReplyId(9))
    if already_deleted:
        _delete(aggregate, UserId(1))
        assert aggregate.deleted is True
    before = _state(aggregate), _events(aggregate)
    assert aggregate.likes
    assert aggregate.mentions
    assert aggregate.reply_ids == {ReplyId(9)}
    assert len(before[1]) == (3 if already_deleted else 2)
    with pytest.raises(exception, match=message):
        if operation == "like":
            aggregate.like(UserId(actor), content_type)
        elif content_type == "invalid_type":
            aggregate.delete(UserId(actor), content_type)
        else:
            _delete(aggregate, UserId(actor))
    assert (_state(aggregate), _events(aggregate)) == before


@pytest.mark.parametrize(("kind", "content_type"), [("post", "reply"), ("reply", "post")])
def test_direct_like_keeps_legacy_cross_kind_behavior(kind, content_type):
    """元の直接likeは集約と異なる種別文字列も受理し、型付き対象IDは集約のものを保つ。"""
    aggregate = _create(kind)
    aggregate.like(UserId(2), content_type)
    assert aggregate.is_liked_by_user(UserId(2)) is True
    _assert_like_event(aggregate.get_events()[-1], aggregate, UserId(2), content_type, True)


def test_deleted_post_still_accepts_like():
    """元の削除済み投稿へのlikeは拒否せず、削除状態を保って反応を追加する。"""
    post = _create("post")
    post.delete_post(UserId(1))
    prefix = _events(post)
    post.like_post(UserId(2))
    assert post.is_liked_by_user(UserId(2)) is True
    assert post.deleted is True
    assert tuple(post.get_events()[:-1]) == prefix
    _assert_like_event(post.get_events()[-1], post, UserId(2), "post", True)


def test_public_mention_changes_preserve_other_entries():
    """空の集合へ公開操作で追加し、指定メンションの除去が他の名前を消さない。"""
    post = _create("post")
    assert post.mentions == set()
    testuser = Mention("testuser", PostId(1))
    post.add_mention(testuser)
    assert len(post.mentions) == 1
    assert testuser in post.mentions
    post.remove_mention(testuser)
    assert testuser not in post.mentions
    for name in ("user1", "user2"):
        post.add_mention(Mention(name, PostId(1)))
    assert post.get_mentioned_users() == {"user1", "user2"}
    post.remove_mention(Mention("user1", PostId(1)))
    assert post.mentions == {Mention("user2", PostId(1))}


@pytest.mark.parametrize(
    ("kind", "body", "hashtags"),
    [
        ("post", "a" * 280, ()),
        ("reply", "あ" * 280, ()),
        ("post", "content", tuple(["#tag"] * 10)),
        ("reply", "テスト", tuple(f"tag{i}" for i in range(10))),
    ],
    ids=["post-ascii280", "reply-japanese280", "post-duplicate-tags10", "reply-unprefixed-tags10"],
)
def test_creation_preserves_boundary_content(kind, body, hashtags):
    """元の長さ境界と重複・接頭辞なしタグを、値の構築だけでなく集約createでもそのまま保持する。"""
    aggregate = _create(kind, PostContent(body, hashtags))
    assert aggregate.content.content == body
    assert aggregate.content.hashtags == hashtags
    assert len(aggregate.content.hashtags) == len(hashtags)


@pytest.mark.parametrize(
    ("parent_post", "parent_reply", "parent_author"), [(PostId(1), ReplyId(2), UserId(2)), (None, None, None)]
)
def test_creation_rejects_invalid_reply_parents(parent_post, parent_reply, parent_author):
    """元の両親あり・両親なしcreateは、無関係な例外ではなく親参照専用の例外で拒否する。"""
    with pytest.raises(InvalidParentReferenceException):
        ReplyAggregate.create(
            ReplyId(1), parent_post, parent_reply, parent_author, UserId(1), PostContent("テスト返信")
        )


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_like_metadata_keeps_distinct_identity_bindings_and_provenance(kind):
    """実行者・受取作者・対象・親の異なる識別子と出典を、いいね追加/解除の実イベントへ正しく渡す。"""
    content = PostContent("出典付き")
    if kind == "post":
        aggregate = PostAggregate.create_from_db(
            PostId(1),
            UserId(1),
            content,
            set(),
            set(),
            set(),
            identity_token=TARGET_TOKEN,
            author_identity_token=AUTHOR_TOKEN,
        )
    else:
        aggregate = ReplyAggregate.create_from_db(
            ReplyId(1),
            PostId(2),
            None,
            UserId(1),
            content,
            set(),
            set(),
            set(),
            identity_token=TARGET_TOKEN,
            author_identity_token=AUTHOR_TOKEN,
            parent_identity_token=PARENT_TOKEN,
        )
    provenance = {"request_id": "aggregate-audit-request", "world_id": 7, "player_id": 8}
    assert aggregate.get_events() == []
    for expected in (True, False):
        if kind == "post":
            aggregate.like_post(UserId(2), "反応者", liker_identity_token=ACTOR_TOKEN, execution_provenance=provenance)
        else:
            aggregate.like_reply(UserId(2), "反応者", liker_identity_token=ACTOR_TOKEN, execution_provenance=provenance)
        event = aggregate.get_events()[-1]
        _assert_like_event(event, aggregate, UserId(2), kind, expected)
        assert event.actor_identity_token == ACTOR_TOKEN
        assert event.recipient_identity_token == AUTHOR_TOKEN
        assert event.target_identity_token == TARGET_TOKEN
        assert event.liker_display_name == "反応者"
        assert event.execution_provenance == {"request_id": "aggregate-audit-request", "world_id": 7, "player_id": 8}
        assert aggregate.parent_identity_token == (PARENT_TOKEN if kind == "reply" else None)
    assert len(aggregate.get_events()) == 2
