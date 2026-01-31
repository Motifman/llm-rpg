"""SNSイベントクラスの包括的なテスト"""

import pytest
from datetime import datetime, timedelta
from ai_rpg_world.domain.sns.event import (
    # User events
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserUnfollowedEvent,
    SnsUserBlockedEvent,
    SnsUserUnblockedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnsubscribedEvent,
    # Post events
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
    SnsContentDeletedEvent,
    SnsContentMentionedEvent,
)
from ai_rpg_world.domain.sns.value_object import UserId, PostId, ReplyId, PostContent, Mention, Like


class TestSnsUserCreatedEvent:
    """SnsUserCreatedEventのテスト"""

    def test_create_user_event_success(self):
        """正常なユーザー作成イベントの作成テスト"""
        event = SnsUserCreatedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            user_id=UserId(1),
            user_name="testuser",
            display_name="テストユーザー",
            bio="テストです"
        )

        assert event.user_id == UserId(1)
        assert event.user_name == "testuser"
        assert event.display_name == "テストユーザー"
        assert event.bio == "テストです"
        assert isinstance(event.event_id, int)
        assert isinstance(event.occurred_at, datetime)
        assert event.aggregate_id == UserId(1)
        assert event.aggregate_type == "UserAggregate"

    def test_user_event_immutability(self):
        """ユーザー作成イベントの不変性テスト"""
        event = SnsUserCreatedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            user_id=UserId(1),
            user_name="testuser",
            display_name="テストユーザー",
            bio="テストです"
        )

        # イベントはfrozen dataclassのため属性変更不可
        with pytest.raises(AttributeError):
            event.user_name = "newname"


class TestSnsUserFollowedEvent:
    """SnsUserFollowedEventのテスト"""

    def test_create_followed_event_success(self):
        """正常なフォローイベントの作成テスト"""
        event = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        assert event.follower_user_id == UserId(1)
        assert event.followee_user_id == UserId(2)
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_followed_event_business_equality(self):
        """フォローイベントのビジネスロジック等価性テスト"""
        event1 = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        event2 = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.follower_user_id == event2.follower_user_id
        assert event1.followee_user_id == event2.followee_user_id
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at

    def test_followed_event_inequality_with_different_follower(self):
        """異なるフォロワーでの不等価性テスト"""
        event1 = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        event2 = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(3),
            followee_user_id=UserId(2)
        )

        assert event1 != event2


class TestSnsUserProfileUpdatedEvent:
    """SnsUserProfileUpdatedEventのテスト"""

    def test_create_profile_updated_event_with_both_fields(self):
        """両方のフィールドを更新するプロフィール更新イベントのテスト"""
        event = SnsUserProfileUpdatedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            user_id=UserId(1),
            new_bio="新しいbio",
            new_display_name="新しい表示名"
        )

        assert event.user_id == UserId(1)
        assert event.new_bio == "新しいbio"
        assert event.new_display_name == "新しい表示名"

    def test_create_profile_updated_event_with_only_bio(self):
        """bioのみ更新するプロフィール更新イベントのテスト"""
        event = SnsUserProfileUpdatedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            user_id=UserId(1),
            new_bio="新しいbio",
            new_display_name=None
        )

        assert event.new_bio == "新しいbio"
        assert event.new_display_name is None


class TestSnsPostCreatedEvent:
    """SnsPostCreatedEventのテスト"""

    def test_create_post_event_success(self):
        """正常なポスト作成イベントの作成テスト"""
        post_id = PostId(1)
        content = PostContent("テスト投稿です")
        mentions = {Mention(mentioned_user_name="testuser", post_id=post_id)}

        event = SnsPostCreatedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            post_id=post_id,
            author_user_id=UserId(1),
            content=content,
            mentions=mentions
        )

        assert event.post_id == post_id
        assert event.author_user_id == UserId(1)
        assert event.content == content
        assert event.mentions == mentions


class TestSnsReplyCreatedEvent:
    """SnsReplyCreatedEventのテスト"""

    def test_create_reply_event_success(self):
        """正常なリプライ作成イベントの作成テスト"""
        reply_id = ReplyId(1)
        post_id = PostId(1)
        content = PostContent("テストリプライです")

        event = SnsReplyCreatedEvent.create(
            aggregate_id=reply_id,
            aggregate_type="ReplyAggregate",
            reply_id=reply_id,
            author_user_id=UserId(1),
            content=content,
            parent_post_id=post_id
        )

        assert event.reply_id == reply_id
        assert event.author_user_id == UserId(1)
        assert event.content == content
        assert event.parent_post_id == post_id
        assert event.parent_reply_id is None


class TestSnsContentLikedEvent:
    """SnsContentLikedEventのテスト"""

    def test_create_like_event_success(self):
        """正常ないいねイベントの作成テスト"""
        post_id = PostId(1)

        event = SnsContentLikedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            target_id=post_id,
            user_id=UserId(2),  # いいねしたユーザー
            content_author_id=UserId(1),  # コンテンツの作成者
            content_type="post"
        )

        assert event.target_id == post_id
        assert event.user_id == UserId(2)
        assert event.content_author_id == UserId(1)
        assert event.content_type == "post"

    def test_like_event_business_equality(self):
        """いいねイベントのビジネスロジック等価性テスト"""
        post_id = PostId(1)

        event1 = SnsContentLikedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            target_id=post_id,
            user_id=UserId(2),
            content_author_id=UserId(1),
            content_type="post"
        )

        event2 = SnsContentLikedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            target_id=post_id,
            user_id=UserId(2),
            content_author_id=UserId(1),
            content_type="post"
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.target_id == event2.target_id
        assert event1.user_id == event2.user_id
        assert event1.content_author_id == event2.content_author_id
        assert event1.content_type == event2.content_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at


class TestSnsContentDeletedEvent:
    """SnsContentDeletedEventのテスト"""

    def test_create_delete_event_success(self):
        """正常な削除イベントの作成テスト"""
        post_id = PostId(1)

        event = SnsContentDeletedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            target_id=post_id,
            author_user_id=UserId(1),
            content_type="post"
        )

        assert event.target_id == post_id
        assert event.author_user_id == UserId(1)
        assert event.content_type == "post"


class TestSnsContentMentionedEvent:
    """SnsContentMentionedEventのテスト"""

    def test_create_mentioned_event_success(self):
        """正常なメンションイベントの作成テスト"""
        post_id = PostId(1)
        mentioned_users = {"user1", "user2"}

        event = SnsContentMentionedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            target_id=post_id,
            mentioned_by_user_id=UserId(1),
            mentioned_user_names=mentioned_users,
            content_type="post"
        )

        assert event.target_id == post_id
        assert event.mentioned_by_user_id == UserId(1)
        assert event.mentioned_user_names == mentioned_users
        assert event.content_type == "post"


class TestEventBaseFunctionality:
    """イベント基底機能のテスト"""

    def test_all_events_have_unique_ids(self):
        """全てのイベントがユニークなIDを持つことをテスト"""
        event1 = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        event2 = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        # 同じパラメータでも異なるevent_idを持つ
        assert event1.event_id != event2.event_id

    def test_all_events_have_current_timestamp(self):
        """全てのイベントが現在のタイムスタンプを持つことをテスト"""
        before_time = datetime.now() - timedelta(seconds=1)

        event = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        after_time = datetime.now() + timedelta(seconds=1)

        assert before_time < event.occurred_at < after_time

    def test_event_immutability(self):
        """全てのイベントが不変であることをテスト"""
        event = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        # イベントはfrozen dataclassのため属性変更不可
        with pytest.raises(AttributeError):
            event.follower_user_id = UserId(3)


class TestEventTypeValidation:
    """イベントタイプのバリデーションテスト"""

    def test_user_events_have_correct_aggregate_type(self):
        """ユーザーイベントが正しい集約タイプを持つことをテスト"""
        event = SnsUserCreatedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            user_id=UserId(1),
            user_name="test",
            display_name="test",
            bio="test"
        )

        assert event.aggregate_type == "UserAggregate"

    def test_content_events_have_correct_aggregate_type(self):
        """コンテンツイベントが正しい集約タイプを持つことをテスト"""
        post_event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("test")
        )

        assert post_event.aggregate_type == "PostAggregate"

        reply_event = SnsReplyCreatedEvent.create(
            aggregate_id=ReplyId(1),
            aggregate_type="ReplyAggregate",
            reply_id=ReplyId(1),
            author_user_id=UserId(1),
            content=PostContent("test")
        )

        assert reply_event.aggregate_type == "ReplyAggregate"


class TestSnsUserUnfollowedEvent:
    """SnsUserUnfollowedEventのテスト"""

    def test_create_unfollowed_event_success(self):
        """正常なフォロー解除イベントの作成テスト"""
        event = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        assert event.follower_user_id == UserId(1)
        assert event.followee_user_id == UserId(2)
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_unfollowed_event_business_equality(self):
        """フォロー解除イベントのビジネスロジック等価性テスト"""
        event1 = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        event2 = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.follower_user_id == event2.follower_user_id
        assert event1.followee_user_id == event2.followee_user_id
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at

    def test_unfollowed_event_inequality_with_different_follower(self):
        """異なるフォロワーでの不等価性テスト"""
        event1 = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        event2 = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(3),
            followee_user_id=UserId(2)
        )

        assert event1 != event2

    def test_unfollowed_event_inequality_with_different_followee(self):
        """異なるフォローイーでの不等価性テスト"""
        event1 = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2)
        )

        event2 = SnsUserUnfollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(4)
        )

        assert event1 != event2


class TestSnsUserBlockedEvent:
    """SnsUserBlockedEventのテスト"""

    def test_create_blocked_event_success(self):
        """正常なブロックイベントの作成テスト"""
        event = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        assert event.blocker_user_id == UserId(1)
        assert event.blocked_user_id == UserId(2)
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_blocked_event_business_equality(self):
        """ブロックイベントのビジネスロジック等価性テスト"""
        event1 = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        event2 = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.blocker_user_id == event2.blocker_user_id
        assert event1.blocked_user_id == event2.blocked_user_id
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at

    def test_blocked_event_inequality_with_different_blocker(self):
        """異なるブロッカーでの不等価性テスト"""
        event1 = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        event2 = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(3),
            blocked_user_id=UserId(2)
        )

        assert event1 != event2

    def test_blocked_event_inequality_with_different_blocked(self):
        """異なるブロック対象での不等価性テスト"""
        event1 = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        event2 = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(4)
        )

        assert event1 != event2


class TestSnsUserUnblockedEvent:
    """SnsUserUnblockedEventのテスト"""

    def test_create_unblocked_event_success(self):
        """正常なブロック解除イベントの作成テスト"""
        event = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        assert event.blocker_user_id == UserId(1)
        assert event.blocked_user_id == UserId(2)
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_unblocked_event_business_equality(self):
        """ブロック解除イベントのビジネスロジック等価性テスト"""
        event1 = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        event2 = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.blocker_user_id == event2.blocker_user_id
        assert event1.blocked_user_id == event2.blocked_user_id
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at

    def test_unblocked_event_inequality_with_different_blocker(self):
        """異なるブロッカーでの不等価性テスト"""
        event1 = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        event2 = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(3),
            blocked_user_id=UserId(2)
        )

        assert event1 != event2

    def test_unblocked_event_inequality_with_different_blocked(self):
        """異なるブロック対象での不等価性テスト"""
        event1 = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        event2 = SnsUserUnblockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(4)
        )

        assert event1 != event2


class TestSnsUserSubscribedEvent:
    """SnsUserSubscribedEventのテスト"""

    def test_create_subscribed_event_success(self):
        """正常なサブスクライブイベントの作成テスト"""
        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        assert event.subscriber_user_id == UserId(1)
        assert event.subscribed_user_id == UserId(2)
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_subscribed_event_business_equality(self):
        """サブスクライブイベントのビジネスロジック等価性テスト"""
        event1 = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        event2 = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.subscriber_user_id == event2.subscriber_user_id
        assert event1.subscribed_user_id == event2.subscribed_user_id
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at

    def test_subscribed_event_inequality_with_different_subscriber(self):
        """異なるサブスクライバーでの不等価性テスト"""
        event1 = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        event2 = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(3),
            subscribed_user_id=UserId(2)
        )

        assert event1 != event2

    def test_subscribed_event_inequality_with_different_subscribed(self):
        """異なるサブスクライブ対象での不等価性テスト"""
        event1 = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        event2 = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(4)
        )

        assert event1 != event2


class TestSnsUserUnsubscribedEvent:
    """SnsUserUnsubscribedEventのテスト"""

    def test_create_unsubscribed_event_success(self):
        """正常なアンサブスクライブイベントの作成テスト"""
        event = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        assert event.subscriber_user_id == UserId(1)
        assert event.subscribed_user_id == UserId(2)
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_unsubscribed_event_business_equality(self):
        """アンサブスクライブイベントのビジネスロジック等価性テスト"""
        event1 = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        event2 = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        # ビジネスロジック的には同じだが、技術的には異なるインスタンス
        assert event1.subscriber_user_id == event2.subscriber_user_id
        assert event1.subscribed_user_id == event2.subscribed_user_id
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        # イベントIDと発生時刻は異なる
        assert event1.event_id != event2.event_id
        assert event1.occurred_at != event2.occurred_at

    def test_unsubscribed_event_inequality_with_different_subscriber(self):
        """異なるサブスクライバーでの不等価性テスト"""
        event1 = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        event2 = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(3),
            subscribed_user_id=UserId(2)
        )

        assert event1 != event2

    def test_unsubscribed_event_inequality_with_different_subscribed(self):
        """異なるサブスクライブ対象での不等価性テスト"""
        event1 = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        event2 = SnsUserUnsubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(4)
        )

        assert event1 != event2
