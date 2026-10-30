"""SNS 集約の外で保持する可変コレクションから内部状態を変更できないことを保証する。"""

import pytest

from ai_rpg_world.domain.sns.aggregate import PostAggregate, ReplyAggregate, UserAggregate
from ai_rpg_world.domain.sns.entity import SnsUser
from ai_rpg_world.domain.sns.value_object import (
    BlockRelationShip,
    FollowRelationShip,
    Like,
    Mention,
    PostContent,
    PostId,
    ReplyId,
    SubscribeRelationShip,
    UserId,
    UserProfile,
)


@pytest.mark.parametrize("relationship", ["follow", "block", "subscribe"])
def test_constructor_does_not_retain_caller_relationship_list(relationship: str) -> None:
    """復元時に渡した関係一覧を呼び出し元で空にしても、集約の関係は消えない。"""
    owner, target = UserId(1), UserId(2)
    relations = {
        "follow": [FollowRelationShip(owner, target)],
        "block": [BlockRelationShip(owner, UserId(3))],
        "subscribe": [SubscribeRelationShip(owner, target)],
    }
    aggregate = UserAggregate(
        owner,
        SnsUser(owner, UserProfile("owner", "所有者", "")),
        relations["follow"],
        relations["block"],
        relations["subscribe"],
    )
    relations[relationship].clear()
    assert len(getattr(aggregate, f"{relationship}_relationships")) == 1
    assert aggregate.get_events() == []


@pytest.mark.parametrize("relationship", ["follow", "block", "subscribe"])
def test_relationship_property_does_not_expose_internal_list(relationship: str) -> None:
    """取得した関係一覧を空にしても、集約の関係は消えない。"""
    owner, target = UserId(1), UserId(2)
    aggregate = UserAggregate(
        owner,
        SnsUser(owner, UserProfile("owner", "所有者", "")),
        [FollowRelationShip(owner, target)],
        [BlockRelationShip(owner, UserId(3))],
        [SubscribeRelationShip(owner, target)],
    )
    getattr(aggregate, f"{relationship}_relationships").clear()
    assert len(getattr(aggregate, f"{relationship}_relationships")) == 1
    assert aggregate.get_events() == []


@pytest.mark.parametrize("kind", ["post", "reply"])
@pytest.mark.parametrize("collection", ["likes", "mentions"])
def test_content_constructor_does_not_retain_caller_sets(kind: str, collection: str) -> None:
    """復元時に渡したいいね・メンション集合を空にしても、投稿と返信の状態は変わらない。"""
    content_id = PostId(1) if kind == "post" else ReplyId(1)
    likes = {Like(UserId(2), content_id)}
    mentions = {Mention("相手", content_id)}
    if kind == "post":
        aggregate = PostAggregate(PostId(1), UserId(1), PostContent("本文"), likes, mentions, set())
    else:
        aggregate = ReplyAggregate(
            ReplyId(1),
            UserId(1),
            PostContent("本文"),
            likes,
            mentions,
            set(),
            parent_post_id=PostId(1),
        )
    {"likes": likes, "mentions": mentions}[collection].clear()
    assert len(getattr(aggregate, collection)) == 1
    assert aggregate.get_events() == []
