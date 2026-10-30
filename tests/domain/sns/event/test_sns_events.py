"""SNSイベントが人物・本文を保持し、別IDと現在UTC時刻で発行されることを守る。"""

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.domain.sns.event import (
    SnsContentDeletedEvent,
    SnsContentLikedEvent,
    SnsContentMentionedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserBlockedEvent,
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnblockedEvent,
    SnsUserUnfollowedEvent,
    SnsUserUnsubscribedEvent,
)
from ai_rpg_world.domain.sns.value_object import Mention, PostContent, PostId, ReplyId, UserId


def _assert_public_payload(event, expected):
    """明示した公開属性だけを独立期待値と比べ、内部の属性一覧は固定しない。"""
    for attribute, value in expected.items():
        if value is None:
            assert getattr(event, attribute) is None, attribute
        else:
            assert getattr(event, attribute) == value, attribute


@pytest.mark.parametrize(
    "event_type, kwargs, expected",
    [
        pytest.param(
            SnsUserCreatedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "user_name": "testuser",
                "display_name": "テストユーザー",
                "bio": "テストです",
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "user_name": "testuser",
                "display_name": "テストユーザー",
                "bio": "テストです",
            },
            id="create_user_event_success",
        ),
        pytest.param(
            SnsUserFollowedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            id="create_followed_event_success",
        ),
        pytest.param(
            SnsUserProfileUpdatedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "new_bio": "新しいbio",
                "new_display_name": "新しい表示名",
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "new_bio": "新しいbio",
                "new_display_name": "新しい表示名",
            },
            id="create_profile_updated_event_with_both_fields",
        ),
        pytest.param(
            SnsUserProfileUpdatedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "new_bio": "新しいbio",
                "new_display_name": None,
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "new_bio": "新しいbio",
                "new_display_name": None,
            },
            id="create_profile_updated_event_with_only_bio",
        ),
        pytest.param(
            SnsPostCreatedEvent,
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "post_id": PostId(1),
                "author_user_id": UserId(1),
                "content": PostContent("テスト投稿です"),
                "mentions": {Mention(mentioned_user_name="testuser", post_id=PostId(1))},
            },
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "post_id": PostId(1),
                "author_user_id": UserId(1),
                "content": PostContent("テスト投稿です"),
                "mentions": {Mention(mentioned_user_name="testuser", post_id=PostId(1))},
            },
            id="create_post_event_success",
        ),
        pytest.param(
            SnsReplyCreatedEvent,
            {
                "aggregate_id": ReplyId(1),
                "aggregate_type": "ReplyAggregate",
                "reply_id": ReplyId(1),
                "author_user_id": UserId(1),
                "content": PostContent("テストリプライです"),
                "parent_post_id": PostId(1),
            },
            {
                "aggregate_id": ReplyId(1),
                "aggregate_type": "ReplyAggregate",
                "reply_id": ReplyId(1),
                "author_user_id": UserId(1),
                "content": PostContent("テストリプライです"),
                "parent_post_id": PostId(1),
                "parent_reply_id": None,
            },
            id="create_reply_event_success",
        ),
        pytest.param(
            SnsContentLikedEvent,
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "user_id": UserId(2),
                "content_author_id": UserId(1),
                "content_type": "post",
            },
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "user_id": UserId(2),
                "content_author_id": UserId(1),
                "content_type": "post",
            },
            id="create_like_event_success",
        ),
        pytest.param(
            SnsContentDeletedEvent,
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "author_user_id": UserId(1),
                "content_type": "post",
            },
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "author_user_id": UserId(1),
                "content_type": "post",
            },
            id="create_delete_event_success",
        ),
        pytest.param(
            SnsContentMentionedEvent,
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "mentioned_by_user_id": UserId(1),
                "mentioned_user_names": {"user1", "user2"},
                "content_type": "post",
            },
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "mentioned_by_user_id": UserId(1),
                "mentioned_user_names": {"user1", "user2"},
                "content_type": "post",
            },
            id="create_mentioned_event_success",
        ),
        pytest.param(
            SnsUserCreatedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "user_name": "test",
                "display_name": "test",
                "bio": "test",
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "user_name": "test",
                "display_name": "test",
                "bio": "test",
            },
            id="user_events_have_correct_aggregate_type",
        ),
        pytest.param(
            SnsPostCreatedEvent,
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "post_id": PostId(1),
                "author_user_id": UserId(1),
                "content": PostContent("test"),
            },
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "post_id": PostId(1),
                "author_user_id": UserId(1),
                "content": PostContent("test"),
            },
            id="content_events_have_correct_aggregate_type-1",
        ),
        pytest.param(
            SnsReplyCreatedEvent,
            {
                "aggregate_id": ReplyId(1),
                "aggregate_type": "ReplyAggregate",
                "reply_id": ReplyId(1),
                "author_user_id": UserId(1),
                "content": PostContent("test"),
            },
            {
                "aggregate_id": ReplyId(1),
                "aggregate_type": "ReplyAggregate",
                "reply_id": ReplyId(1),
                "author_user_id": UserId(1),
                "content": PostContent("test"),
                "parent_reply_id": None,
            },
            id="content_events_have_correct_aggregate_type-2",
        ),
        pytest.param(
            SnsUserUnfollowedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            id="create_unfollowed_event_success",
        ),
        pytest.param(
            SnsUserBlockedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            id="create_blocked_event_success",
        ),
        pytest.param(
            SnsUserUnblockedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            id="create_unblocked_event_success",
        ),
        pytest.param(
            SnsUserSubscribedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            id="create_subscribed_event_success",
        ),
        pytest.param(
            SnsUserUnsubscribedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            id="create_unsubscribed_event_success",
        ),
    ],
)
def test_event_payload_fields(event_type, kwargs, expected):
    """生成時に指定した人物・本文・親・メンションと、省略時のNoneを保持する。"""
    event = event_type.create(**kwargs)

    _assert_public_payload(event, expected)
    assert isinstance(event.event_id, int)
    assert isinstance(event.occurred_at, datetime)


@pytest.mark.parametrize(
    "event_type, actor, target, changed_actor, changed_target, expected_second",
    [
        pytest.param(
            SnsUserFollowedEvent,
            "follower_user_id",
            "followee_user_id",
            UserId(3),
            UserId(2),
            (UserId(3), UserId(2)),
            id="followed_event_inequality_with_different_follower",
        ),
        pytest.param(
            SnsUserUnfollowedEvent,
            "follower_user_id",
            "followee_user_id",
            UserId(3),
            UserId(2),
            (UserId(3), UserId(2)),
            id="unfollowed_event_inequality_with_different_follower",
        ),
        pytest.param(
            SnsUserUnfollowedEvent,
            "follower_user_id",
            "followee_user_id",
            UserId(1),
            UserId(4),
            (UserId(1), UserId(4)),
            id="unfollowed_event_inequality_with_different_followee",
        ),
        pytest.param(
            SnsUserBlockedEvent,
            "blocker_user_id",
            "blocked_user_id",
            UserId(3),
            UserId(2),
            (UserId(3), UserId(2)),
            id="blocked_event_inequality_with_different_blocker",
        ),
        pytest.param(
            SnsUserBlockedEvent,
            "blocker_user_id",
            "blocked_user_id",
            UserId(1),
            UserId(4),
            (UserId(1), UserId(4)),
            id="blocked_event_inequality_with_different_blocked",
        ),
        pytest.param(
            SnsUserUnblockedEvent,
            "blocker_user_id",
            "blocked_user_id",
            UserId(3),
            UserId(2),
            (UserId(3), UserId(2)),
            id="unblocked_event_inequality_with_different_blocker",
        ),
        pytest.param(
            SnsUserUnblockedEvent,
            "blocker_user_id",
            "blocked_user_id",
            UserId(1),
            UserId(4),
            (UserId(1), UserId(4)),
            id="unblocked_event_inequality_with_different_blocked",
        ),
        pytest.param(
            SnsUserSubscribedEvent,
            "subscriber_user_id",
            "subscribed_user_id",
            UserId(3),
            UserId(2),
            (UserId(3), UserId(2)),
            id="subscribed_event_inequality_with_different_subscriber",
        ),
        pytest.param(
            SnsUserSubscribedEvent,
            "subscriber_user_id",
            "subscribed_user_id",
            UserId(1),
            UserId(4),
            (UserId(1), UserId(4)),
            id="subscribed_event_inequality_with_different_subscribed",
        ),
        pytest.param(
            SnsUserUnsubscribedEvent,
            "subscriber_user_id",
            "subscribed_user_id",
            UserId(3),
            UserId(2),
            (UserId(3), UserId(2)),
            id="unsubscribed_event_inequality_with_different_subscriber",
        ),
        pytest.param(
            SnsUserUnsubscribedEvent,
            "subscriber_user_id",
            "subscribed_user_id",
            UserId(1),
            UserId(4),
            (UserId(1), UserId(4)),
            id="unsubscribed_event_inequality_with_different_subscribed",
        ),
    ],
)
def test_changed_people_are_preserved(event_type, actor, target, changed_actor, changed_target, expected_second):
    """人物の片側が変わったとき、両イベントの実行者と対象を取り違えず保持する。"""
    event1 = event_type.create(
        aggregate_id=UserId(1),
        aggregate_type="UserAggregate",
        **{actor: UserId(1), target: UserId(2)},
    )
    event2 = event_type.create(
        aggregate_id=UserId(1),
        aggregate_type="UserAggregate",
        **{actor: changed_actor, target: changed_target},
    )

    assert (getattr(event1, actor), getattr(event1, target)) == (UserId(1), UserId(2))
    assert (getattr(event2, actor), getattr(event2, target)) == expected_second


@pytest.mark.parametrize(
    "event_type, kwargs, expected",
    [
        pytest.param(
            SnsUserFollowedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            id="followed_event",
        ),
        pytest.param(
            SnsContentLikedEvent,
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "user_id": UserId(2),
                "content_author_id": UserId(1),
                "content_type": "post",
            },
            {
                "aggregate_id": PostId(1),
                "aggregate_type": "PostAggregate",
                "target_id": PostId(1),
                "user_id": UserId(2),
                "content_author_id": UserId(1),
                "content_type": "post",
            },
            id="like_event",
        ),
        pytest.param(
            SnsUserUnfollowedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            id="unfollowed_event",
        ),
        pytest.param(
            SnsUserBlockedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            id="blocked_event",
        ),
        pytest.param(
            SnsUserUnblockedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "blocker_user_id": UserId(1),
                "blocked_user_id": UserId(2),
            },
            id="unblocked_event",
        ),
        pytest.param(
            SnsUserSubscribedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            id="subscribed_event",
        ),
        pytest.param(
            SnsUserUnsubscribedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "subscriber_user_id": UserId(1),
                "subscribed_user_id": UserId(2),
            },
            id="unsubscribed_event",
        ),
    ],
)
def test_repeated_events_keep_payload_and_fresh_metadata(event_type, kwargs, expected):
    """同じ内容を二回生成してもIDは別になり、各回に現在のUTC時刻を付ける。"""
    events = []
    for _ in range(2):
        before = datetime.now(timezone.utc)
        event = event_type.create(**kwargs)
        after = datetime.now(timezone.utc)
        events.append(event)

        _assert_public_payload(event, expected)
        assert isinstance(event.event_id, int)
        assert isinstance(event.occurred_at, datetime)
        # #311の回帰を保持する。時刻の分解能による二回の非等価は要求しない。
        assert event.occurred_at.tzinfo is not None
        assert event.occurred_at.utcoffset() == timedelta(0)
        assert before <= event.occurred_at <= after

    assert events[0].event_id != events[1].event_id


@pytest.mark.parametrize(
    "event_type, kwargs, attribute, replacement, original",
    [
        pytest.param(
            SnsUserCreatedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "user_id": UserId(1),
                "user_name": "testuser",
                "display_name": "テストユーザー",
                "bio": "テストです",
            },
            "user_name",
            "newname",
            "testuser",
            id="user_event_immutability",
        ),
        pytest.param(
            SnsUserFollowedEvent,
            {
                "aggregate_id": UserId(1),
                "aggregate_type": "UserAggregate",
                "follower_user_id": UserId(1),
                "followee_user_id": UserId(2),
            },
            "follower_user_id",
            UserId(3),
            UserId(1),
            id="event_immutability",
        ),
    ],
)
def test_event_reassignment_is_rejected(event_type, kwargs, attribute, replacement, original):
    """公開属性への通常の再代入を拒否し、拒否後も元の人物や名前が変わらない。"""
    event = event_type.create(**kwargs)

    with pytest.raises(AttributeError):
        setattr(event, attribute, replacement)

    assert getattr(event, attribute) == original
