from typing import List
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.sns.sns_user import SnsUser
from src.domain.sns.follow import FollowRelationShip
from src.domain.sns.block import BlockRelationShip
from src.domain.sns.subscribe import SubscribeRelationShip
from src.domain.sns.sns_user_event import SnsUserFollowedEvent, SnsUserUnfollowedEvent, SnsUserBlockedEvent, SnsUserUnblockedEvent, SnsUserProfileUpdatedEvent
from src.domain.sns.base_sns_event import SnsUserSubscribedEvent, SnsUserUnsubscribedEvent


class UserAggregate(AggregateRoot):
    def __init__(
        self,
        user_id: int,
        sns_user: SnsUser,
        follow_relationships: List[FollowRelationShip],
        block_relationships: List[BlockRelationShip],
        subscribe_relationships: List[SubscribeRelationShip],
    ):
        super().__init__()
        self._user_id = user_id
        self._sns_user = sns_user
        self._follow_relationships = follow_relationships
        self._block_relationships = block_relationships
        self._subscribe_relationships = subscribe_relationships
        
    def follow(self, followee_user_id: int):
        """ユーザーをフォロー"""
        if self.is_blocked(followee_user_id):
            raise ValueError("Cannot follow a blocked user")
        self._follow_relationships.append(FollowRelationShip(follower_user_id=self._user_id, followee_user_id=followee_user_id))
        event = SnsUserFollowedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            follower_user_id=self._user_id,
            followee_user_id=followee_user_id
        )
        self.add_event(event)
        
    def unfollow(self, followee_user_id: int):
        """ユーザーのフォローを解除"""
        if not self.is_following(followee_user_id):
            raise ValueError("Cannot unfollow a user who is not followed")
        self._follow_relationships = [follow for follow in self._follow_relationships if follow.followee_user_id != followee_user_id]
        event = SnsUserUnfollowedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            follower_user_id=self._user_id,
            followee_user_id=followee_user_id
        )
        self.add_event(event)
        
    def block(self, blocked_user_id: int):
        """ユーザーをブロック"""
        if self.is_blocked(blocked_user_id):
            raise ValueError("Cannot block a blocked user")
        self._block_relationships.append(BlockRelationShip(blocker_user_id=self._user_id, blocked_user_id=blocked_user_id))
        self.unfollow(blocked_user_id)  # ブロックしたユーザーをフォロー解除, ブロックされたユーザーからのフォローはイベントを通じて解除
        self.unsubscribe(blocked_user_id)  # ブロックしたユーザーを購読解除, ブロックされたユーザーからの購読はイベントを通じて解除
        event = SnsUserBlockedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=self._user_id,
            blocked_user_id=blocked_user_id
        )
        self.add_event(event)
        
    def unblock(self, blocked_user_id: int):
        """ユーザーのブロックを解除"""
        if not self.is_blocked(blocked_user_id):
            raise ValueError("Cannot unblock a user who is not blocked")
        self._block_relationships = [block for block in self._block_relationships if block.blocked_user_id != blocked_user_id]
        event = SnsUserUnblockedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=self._user_id,
            blocked_user_id=blocked_user_id
        )
        self.add_event(event)
        
    def subscribe(self, subscribed_user_id: int):
        """ユーザーを購読"""
        if self.is_subscribed(subscribed_user_id):
            raise ValueError("Cannot subscribe to a user who is already subscribed")
        if self.is_blocked(subscribed_user_id):
            raise ValueError("Cannot subscribe to a blocked user")
        if not self.is_following(subscribed_user_id):
            raise ValueError("Cannot subscribe to a user who is not followed")
        self._subscribe_relationships.append(SubscribeRelationShip(subscriber_user_id=self._user_id, subscribed_user_id=subscribed_user_id))
        event = SnsUserSubscribedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            from_user_id=self._user_id,
            to_user_id=subscribed_user_id
        )
        self.add_event(event)
        
    def unsubscribe(self, subscribed_user_id: int):
        """ユーザーの購読を解除"""
        if not self.is_subscribed(subscribed_user_id):
            raise ValueError("Cannot unsubscribe from a user who is not subscribed")
        self._subscribe_relationships = [subscribe for subscribe in self._subscribe_relationships if subscribe.subscribed_user_id != subscribed_user_id]
        event = SnsUserUnsubscribedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            from_user_id=self._user_id,
            to_user_id=subscribed_user_id
        )
        self.add_event(event)

    def is_following(self, user_id: int) -> bool:
        """指定したユーザーをフォローしているか"""
        return any(follow.followee_user_id == user_id for follow in self._follow_relationships)

    def is_blocked(self, user_id: int) -> bool:
        """指定したユーザーをブロックしているか"""
        return any(block.blocked_user_id == user_id for block in self._block_relationships)

    def is_subscribed(self, user_id: int) -> bool:
        """指定したユーザーを購読しているか"""
        return any(subscribe.subscribed_user_id == user_id for subscribe in self._subscribe_relationships)

    def update_user_profile(self, new_bio: str, new_display_name: str):
        """ユーザーのプロフィールを更新"""
        new_user_profile = self._sns_user.user_profile.update_bio(new_bio).update_display_name(new_display_name)
        self._sns_user.update_user_profile(new_user_profile)
        event = SnsUserProfileUpdatedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            user_id=self._user_id,
            new_bio=new_bio,
            new_display_name=new_display_name
        )
        self.add_event(event)