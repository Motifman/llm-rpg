import pytest
from datetime import datetime
from ai_rpg_world.domain.sns.aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity import SnsUser
from ai_rpg_world.domain.sns.value_object import UserProfile, UserId, FollowRelationShip, BlockRelationShip, SubscribeRelationShip
from ai_rpg_world.domain.sns.event import (
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserUnfollowedEvent,
    SnsUserBlockedEvent,
    SnsUserUnblockedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnsubscribedEvent
)
from ai_rpg_world.domain.sns.exception import (
    CannotFollowBlockedUserException,
    CannotUnfollowNotFollowedUserException,
    CannotBlockAlreadyBlockedUserException,
    CannotUnblockNotBlockedUserException,
    CannotSubscribeAlreadySubscribedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    CannotUnsubscribeNotSubscribedUserException,
)


class TestUserAggregate:
    """UserAggregate集約のテスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.user_id = 1
        self.user_profile = UserProfile("testuser", "テストユーザー", "テストです")
        self.sns_user = SnsUser(self.user_id, self.user_profile)

        # 空の関係性リストで集約を作成
        self.aggregate = UserAggregate(
            user_id=self.user_id,
            sns_user=self.sns_user,
            follow_relationships=[],
            block_relationships=[],
            subscribe_relationships=[]
        )

    def test_create_user_aggregate_success(self):
        """正常なUserAggregateの作成テスト"""
        assert self.aggregate._user_id == self.user_id
        assert self.aggregate._sns_user == self.sns_user
        assert self.aggregate._follow_relationships == []
        assert self.aggregate._block_relationships == []
        assert self.aggregate._subscribe_relationships == []

    def test_follow_user_success(self):
        """ユーザーフォローの成功テスト"""
        target_user_id = 2

        self.aggregate.follow(target_user_id)

        # フォローリレーションシップが追加されている
        assert len(self.aggregate._follow_relationships) == 1
        follow = self.aggregate._follow_relationships[0]
        assert follow.follower_user_id == self.user_id
        assert follow.followee_user_id == target_user_id

    def test_follow_blocked_user_raises_error(self):
        """ブロックされたユーザーのフォローが失敗するテスト"""
        target_user_id = 2

        # まずユーザーをブロック
        self.aggregate.block(target_user_id)

        # ブロックされたユーザーをフォローしようとする
        with pytest.raises(CannotFollowBlockedUserException):
            self.aggregate.follow(target_user_id)

    def test_unfollow_user_success(self):
        """ユーザーフォロー解除の成功テスト"""
        target_user_id = 2

        # まずフォロー
        self.aggregate.follow(target_user_id)

        # フォロー解除
        self.aggregate.unfollow(target_user_id)

        # フォローリレーションシップが削除されている
        assert len(self.aggregate._follow_relationships) == 0

    def test_unfollow_not_followed_user_raises_error(self):
        """フォローしていないユーザーのフォロー解除が失敗するテスト"""
        target_user_id = 2

        with pytest.raises(CannotUnfollowNotFollowedUserException):
            self.aggregate.unfollow(target_user_id)

    def test_block_user_success(self):
        """ユーザーブロックの成功テスト"""
        target_user_id = 2

        self.aggregate.block(target_user_id)

        # ブロックリレーションシップが追加されている
        assert len(self.aggregate._block_relationships) == 1
        block = self.aggregate._block_relationships[0]
        assert block.blocker_user_id == self.user_id
        assert block.blocked_user_id == target_user_id

    def test_unblock_user_success(self):
        """ユーザーブロック解除の成功テスト"""
        target_user_id = 2

        # まずブロック
        self.aggregate.block(target_user_id)

        # ブロック解除
        self.aggregate.unblock(target_user_id)

        # ブロックリレーションシップが削除されている
        assert len(self.aggregate._block_relationships) == 0

    def test_subscribe_user_success(self):
        """ユーザー購読の成功テスト"""
        target_user_id = 2

        # まずフォロー
        self.aggregate.follow(target_user_id)

        # 購読
        self.aggregate.subscribe(target_user_id)

        # 購読リレーションシップが追加されている
        assert len(self.aggregate._subscribe_relationships) == 1
        subscribe = self.aggregate._subscribe_relationships[0]
        assert subscribe.subscriber_user_id == self.user_id
        assert subscribe.subscribed_user_id == target_user_id

    def test_subscribe_not_followed_user_raises_error(self):
        """フォローしていないユーザーの購読が失敗するテスト"""
        target_user_id = 2

        with pytest.raises(CannotSubscribeNotFollowedUserException):
            self.aggregate.subscribe(target_user_id)

    def test_unsubscribe_user_success(self):
        """ユーザー購読解除の成功テスト"""
        target_user_id = 2

        # まずフォローして購読
        self.aggregate.follow(target_user_id)
        self.aggregate.subscribe(target_user_id)

        # 購読解除
        self.aggregate.unsubscribe(target_user_id)

        # 購読リレーションシップが削除されている
        assert len(self.aggregate._subscribe_relationships) == 0

    def test_update_user_profile_success(self):
        """ユーザープロフィール更新の成功テスト"""
        new_bio = "新しいbio"
        new_display_name = "新しい表示名"

        self.aggregate.update_user_profile(new_bio, new_display_name)

        # プロフィールが更新されている
        updated_profile = self.aggregate._sns_user.user_profile
        assert updated_profile.bio == new_bio
        assert updated_profile.display_name == new_display_name
        assert updated_profile.user_name == self.user_profile.user_name  # ユーザー名は変更されない

    def test_block_removes_follow_and_subscribe(self):
        """ブロックがフォローと購読を解除することを確認"""
        target_user_id = 2

        # フォローして購読
        self.aggregate.follow(target_user_id)
        self.aggregate.subscribe(target_user_id)

        # ブロック
        self.aggregate.block(target_user_id)

        # フォローと購読が解除されている
        assert len(self.aggregate._follow_relationships) == 0
        assert len(self.aggregate._subscribe_relationships) == 0
        assert len(self.aggregate._block_relationships) == 1

    def test_create_new_user_generates_event(self):
        """create_new_userが正しいイベントを生成することを確認"""
        user_id = UserId(1)
        user_name = "testuser"
        display_name = "テストユーザー"
        bio = "テストです"

        aggregate = UserAggregate.create_new_user(user_id, user_name, display_name, bio)

        # イベントが生成されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserCreatedEvent)
        assert event.user_id == user_id
        assert event.user_name == user_name
        assert event.display_name == display_name
        assert event.bio == bio
        assert event.aggregate_id == user_id
        assert event.aggregate_type == "UserAggregate"

    def test_follow_generates_event(self):
        """followが正しいイベントを生成することを確認"""
        target_user_id = UserId(2)

        self.aggregate.follow(target_user_id)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserFollowedEvent)
        assert event.follower_user_id == self.user_id
        assert event.followee_user_id == target_user_id
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_unfollow_generates_event(self):
        """unfollowが正しいイベントを生成することを確認"""
        target_user_id = UserId(2)

        # まずフォロー
        self.aggregate.follow(target_user_id)

        # イベントをクリア
        self.aggregate.clear_events()

        # フォロー解除
        self.aggregate.unfollow(target_user_id)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserUnfollowedEvent)
        assert event.follower_user_id == self.user_id
        assert event.followee_user_id == target_user_id
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_block_generates_event(self):
        """blockが正しいイベントを生成することを確認"""
        target_user_id = UserId(2)

        self.aggregate.block(target_user_id)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserBlockedEvent)
        assert event.blocker_user_id == self.user_id
        assert event.blocked_user_id == target_user_id
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_unblock_generates_event(self):
        """unblockが正しいイベントを生成することを確認"""
        target_user_id = UserId(2)

        # まずブロック
        self.aggregate.block(target_user_id)

        # イベントをクリア
        self.aggregate.clear_events()

        # ブロック解除
        self.aggregate.unblock(target_user_id)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserUnblockedEvent)
        assert event.blocker_user_id == self.user_id
        assert event.blocked_user_id == target_user_id
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_subscribe_generates_event(self):
        """subscribeが正しいイベントを生成することを確認"""
        target_user_id = UserId(2)

        # まずフォロー
        self.aggregate.follow(target_user_id)

        # イベントをクリア
        self.aggregate.clear_events()

        # 購読
        self.aggregate.subscribe(target_user_id)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserSubscribedEvent)
        assert event.subscriber_user_id == self.user_id
        assert event.subscribed_user_id == target_user_id
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_unsubscribe_generates_event(self):
        """unsubscribeが正しいイベントを生成することを確認"""
        target_user_id = UserId(2)

        # まずフォローして購読
        self.aggregate.follow(target_user_id)
        self.aggregate.subscribe(target_user_id)

        # イベントをクリア
        self.aggregate.clear_events()

        # 購読解除
        self.aggregate.unsubscribe(target_user_id)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserUnsubscribedEvent)
        assert event.subscriber_user_id == self.user_id
        assert event.subscribed_user_id == target_user_id
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_update_profile_generates_event(self):
        """update_user_profileが正しいイベントを生成することを確認"""
        new_bio = "新しいbio"
        new_display_name = "新しい表示名"

        self.aggregate.update_user_profile(new_bio, new_display_name)

        # イベントが生成されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, SnsUserProfileUpdatedEvent)
        assert event.user_id == self.user_id
        assert event.new_bio == new_bio
        assert event.new_display_name == new_display_name
        assert event.aggregate_id == self.user_id
        assert event.aggregate_type == "UserAggregate"

    def test_multiple_events_are_accumulated(self):
        """複数の操作で複数のイベントが蓄積されることを確認"""
        target_user_id = UserId(2)

        # 複数の操作を実行
        self.aggregate.follow(target_user_id)
        self.aggregate.subscribe(target_user_id)
        self.aggregate.update_user_profile("新しいbio", "新しい名前")

        # 全てのイベントが蓄積されていることを確認
        events = self.aggregate.get_events()
        assert len(events) == 3

        # イベントの種類を確認
        event_types = [type(event).__name__ for event in events]
        assert "SnsUserFollowedEvent" in event_types
        assert "SnsUserSubscribedEvent" in event_types
        assert "SnsUserProfileUpdatedEvent" in event_types

