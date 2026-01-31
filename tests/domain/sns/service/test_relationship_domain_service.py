"""
RelationshipDomainServiceのテスト
"""

import pytest
from ai_rpg_world.domain.sns.service.relationship_domain_service import RelationshipDomainService
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity.sns_user import SnsUser
from ai_rpg_world.domain.sns.value_object.user_profile import UserProfile
from ai_rpg_world.domain.sns.value_object.follow import FollowRelationShip
from ai_rpg_world.domain.sns.value_object.block import BlockRelationShip
from ai_rpg_world.domain.sns.value_object.subscribe import SubscribeRelationShip
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.exception import (
    CannotFollowBlockedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    SelfSubscribeException,
)


def create_test_user_aggregate(
    user_id: int,
    follows: list = None,
    blocks: list = None,
    subscribes: list = None
) -> UserAggregate:
    """テスト用のUserAggregateを作成するヘルパー関数"""
    profile = UserProfile(f"user{user_id}", f"User {user_id}", f"Test user {user_id}")
    sns_user = SnsUser(UserId(user_id), profile)

    follows = follows or []
    blocks = blocks or []
    subscribes = subscribes or []

    return UserAggregate(UserId(user_id), sns_user, follows, blocks, subscribes)


class TestRelationshipDomainService:
    """RelationshipDomainServiceのテストクラス"""

    def test_can_follow_success(self):
        """can_follow - 正常系テスト（ブロックされていない場合）"""
        # Given
        follower = create_test_user_aggregate(1)  # フォローするユーザー
        followee = create_test_user_aggregate(2)  # フォローされるユーザー（ブロックなし）

        # When & Then
        # 例外が発生しないことを確認
        RelationshipDomainService.can_follow(follower, followee)

    def test_can_follow_blocked_user_raises_exception(self):
        """can_follow - 異常系テスト（フォローされる側がフォローする側をブロックしている場合）"""
        # Given
        follower = create_test_user_aggregate(1)  # フォローするユーザー
        followee = create_test_user_aggregate(
            2,
            blocks=[BlockRelationShip(UserId(2), UserId(1))]  # ユーザー2がユーザー1をブロック
        )

        # When & Then
        with pytest.raises(CannotFollowBlockedUserException) as exc_info:
            RelationshipDomainService.can_follow(follower, followee)

        assert exc_info.value.follower_user_id == 1
        assert exc_info.value.followee_user_id == 2

    def test_can_subscribe_success(self):
        """can_subscribe - 正常系テスト（フォローしていてブロックされていない場合）"""
        # Given
        subscriber = create_test_user_aggregate(
            1,
            follows=[FollowRelationShip(UserId(1), UserId(2))]  # ユーザー1がユーザー2をフォロー
        )
        subscribed = create_test_user_aggregate(2)  # 購読されるユーザー（ブロックなし）

        # When & Then
        # 例外が発生しないことを確認
        RelationshipDomainService.can_subscribe(subscriber, subscribed)

    def test_can_subscribe_not_followed_raises_exception(self):
        """can_subscribe - 異常系テスト（フォローしていない場合）"""
        # Given
        subscriber = create_test_user_aggregate(1)  # フォロー関係なし
        subscribed = create_test_user_aggregate(2)

        # When & Then
        with pytest.raises(CannotSubscribeNotFollowedUserException) as exc_info:
            RelationshipDomainService.can_subscribe(subscriber, subscribed)

        assert exc_info.value.subscriber_user_id == 1
        assert exc_info.value.subscribed_user_id == 2

    def test_can_subscribe_self_subscribe_raises_exception(self):
        """can_subscribe - 異常系テスト（自分自身を購読しようとした場合）"""
        # Given
        user = create_test_user_aggregate(1)

        # When & Then
        with pytest.raises(SelfSubscribeException) as exc_info:
            RelationshipDomainService.can_subscribe(user, user)

        assert exc_info.value.user_id == 1

    def test_can_subscribe_blocked_user_raises_exception(self):
        """can_subscribe - 異常系テスト（フォローしているが購読される側が購読する側をブロックしている場合）"""
        # Given
        subscriber = create_test_user_aggregate(
            1,
            follows=[FollowRelationShip(UserId(1), UserId(2))]  # フォロー関係あり
        )
        subscribed = create_test_user_aggregate(
            2,
            blocks=[BlockRelationShip(UserId(2), UserId(1))]  # ユーザー2がユーザー1をブロック
        )

        # When & Then
        with pytest.raises(CannotSubscribeBlockedUserException) as exc_info:
            RelationshipDomainService.can_subscribe(subscriber, subscribed)

        assert exc_info.value.subscriber_user_id == 1
        assert exc_info.value.subscribed_user_id == 2
