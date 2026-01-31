"""
関係性ドメインサービス
複数のユーザー集約をまたがるビジネスロジックを実装
"""

from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.exception import (
    CannotFollowBlockedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    SelfSubscribeException,
)


class RelationshipDomainService:
    """関係性に関するドメインサービス"""

    @staticmethod
    def can_follow(follower_aggregate: UserAggregate, followee_aggregate: UserAggregate) -> None:
        """
        フォロー可能かどうかをチェックする

        Args:
            follower_aggregate: フォローする側のユーザー集約
            followee_aggregate: フォローされる側のユーザー集約

        Raises:
            CannotFollowBlockedUserException: フォローされる側がフォローする側をブロックしている場合
        """
        follower_user_id = int(follower_aggregate.user_id)
        followee_user_id = int(followee_aggregate.user_id)

        # フォローされる側がフォローする側をブロックしている場合
        if followee_aggregate.is_blocked(follower_aggregate.user_id):
            raise CannotFollowBlockedUserException(follower_user_id, followee_user_id)

    @staticmethod
    def can_subscribe(subscriber_aggregate: UserAggregate, subscribed_aggregate: UserAggregate) -> None:
        """
        購読可能かどうかをチェックする

        Args:
            subscriber_aggregate: 購読する側のユーザー集約
            subscribed_aggregate: 購読される側のユーザー集約

        Raises:
            SelfSubscribeException: 自分自身を購読しようとした場合
            CannotSubscribeNotFollowedUserException: フォロー関係がない場合
            CannotSubscribeBlockedUserException: 購読される側が購読する側をブロックしている場合
        """
        subscriber_user_id = int(subscriber_aggregate.user_id)
        subscribed_user_id = int(subscribed_aggregate.user_id)

        # 自分自身を購読しようとしている場合
        if subscriber_user_id == subscribed_user_id:
            raise SelfSubscribeException(subscriber_user_id)

        # まずフォロー関係があるかをチェック
        if not subscriber_aggregate.is_following(subscribed_aggregate.user_id):
            raise CannotSubscribeNotFollowedUserException(subscriber_user_id, subscribed_user_id)

        # 購読される側が購読する側をブロックしている場合
        if subscribed_aggregate.is_blocked(subscriber_aggregate.user_id):
            raise CannotSubscribeBlockedUserException(subscriber_user_id, subscribed_user_id)
