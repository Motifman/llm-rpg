import pytest
from datetime import datetime
from src.domain.sns.user_aggregate import UserAggregate
from src.domain.sns.sns_user import SnsUser
from src.domain.sns.user_profile import UserProfile
from src.domain.sns.follow import FollowRelationShip
from src.domain.sns.block import BlockRelationShip
from src.domain.sns.subscribe import SubscribeRelationShip
from src.domain.sns.sns_user_event import (
    SnsUserFollowedEvent, SnsUserUnfollowedEvent,
    SnsUserBlockedEvent, SnsUserUnblockedEvent,
    SnsUserProfileUpdatedEvent
)
from src.domain.sns.base_sns_event import SnsUserSubscribedEvent, SnsUserUnsubscribedEvent


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
        with pytest.raises(ValueError, match="Cannot follow a blocked user"):
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

        with pytest.raises(ValueError, match="Cannot unfollow a user who is not followed"):
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

        with pytest.raises(ValueError, match="Cannot subscribe to a user who is not followed"):
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

