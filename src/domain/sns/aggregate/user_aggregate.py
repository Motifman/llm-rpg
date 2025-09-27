from typing import List, Optional
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.sns.entity import SnsUser
from src.domain.sns.value_object import UserId, UserProfile, FollowRelationShip, BlockRelationShip, SubscribeRelationShip
from src.domain.sns.event import (
    SnsUserFollowedEvent,
    SnsUserUnfollowedEvent,
    SnsUserBlockedEvent,
    SnsUserUnblockedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserCreatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnsubscribedEvent
)
from src.domain.sns.exception import (
    CannotFollowBlockedUserException,
    CannotUnfollowNotFollowedUserException,
    CannotBlockAlreadyBlockedUserException,
    CannotUnblockNotBlockedUserException,
    CannotSubscribeAlreadySubscribedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    CannotUnsubscribeNotSubscribedUserException,
    SelfFollowException,
    SelfUnfollowException,
    SelfBlockException,
    SelfUnblockException,
    SelfSubscribeException,
    SelfUnsubscribeException,
    ProfileUpdateValidationException,
)


class UserAggregate(AggregateRoot):
    def __init__(
        self,
        user_id: UserId,
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
    
    @classmethod
    def create_new_user(cls, user_id: UserId, user_name: str, display_name: str, bio: str) -> "UserAggregate":
        """新しいユーザーを作成"""
        user_profile = UserProfile(user_name, display_name, bio)
        sns_user = SnsUser(user_id, user_profile)
        event = SnsUserCreatedEvent.create(
            aggregate_id=user_id,
            aggregate_type="UserAggregate",
            user_id=user_id,
            user_name=user_name,
            display_name=display_name,
            bio=bio
        )
        user_aggregate = cls(user_id=user_id, sns_user=sns_user, follow_relationships=[], block_relationships=[], subscribe_relationships=[])
        user_aggregate.add_event(event)
        return user_aggregate
    
    @property
    def user_id(self) -> UserId:
        return self._user_id
    
    @property
    def sns_user(self) -> SnsUser:
        return self._sns_user
    
    @property
    def follow_relationships(self) -> List[FollowRelationShip]:
        return self._follow_relationships
    
    @property
    def block_relationships(self) -> List[BlockRelationShip]:
        return self._block_relationships
    
    @property
    def subscribe_relationships(self) -> List[SubscribeRelationShip]:
        return self._subscribe_relationships
        
    def follow(self, followee_user_id: UserId):
        """ユーザーをフォロー"""
        # 自分自身をフォローしようとしていないかチェック
        if self._user_id == followee_user_id:
            raise SelfFollowException(int(self._user_id))

        if self.is_blocked(followee_user_id):
            raise CannotFollowBlockedUserException(int(self._user_id), int(followee_user_id))
        self._follow_relationships.append(FollowRelationShip(follower_user_id=self._user_id, followee_user_id=followee_user_id))
        event = SnsUserFollowedEvent.create(
            aggregate_id=int(self._user_id),
            aggregate_type="UserAggregate",
            follower_user_id=self._user_id,
            followee_user_id=followee_user_id
        )
        self.add_event(event)

    def unfollow(self, followee_user_id: UserId):
        """ユーザーのフォローを解除"""
        # 自分自身をアンフォローしようとしていないかチェック
        if self._user_id == followee_user_id:
            raise SelfUnfollowException(int(self._user_id))

        if not self.is_following(followee_user_id):
            raise CannotUnfollowNotFollowedUserException(int(self._user_id), int(followee_user_id))
        self._follow_relationships = [follow for follow in self._follow_relationships if follow.followee_user_id != followee_user_id]
        event = SnsUserUnfollowedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            follower_user_id=self._user_id,
            followee_user_id=followee_user_id
        )
        self.add_event(event)

    def block(self, blocked_user_id: UserId):
        """ユーザーをブロック"""
        # 自分自身をブロックしようとしていないかチェック
        if self._user_id == blocked_user_id:
            raise SelfBlockException(int(self._user_id))

        if self.is_blocked(blocked_user_id):
            raise CannotBlockAlreadyBlockedUserException(int(self._user_id), int(blocked_user_id))
        self._block_relationships.append(BlockRelationShip(blocker_user_id=self._user_id, blocked_user_id=blocked_user_id))

        # 既にフォローしている場合のみフォロー解除
        if self.is_following(blocked_user_id):
            self.unfollow(blocked_user_id)

        # 既に購読している場合のみ購読解除
        if self.is_subscribed(blocked_user_id):
            self.unsubscribe(blocked_user_id)

        event = SnsUserBlockedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=self._user_id,
            blocked_user_id=blocked_user_id
        )
        self.add_event(event)

    def unblock(self, blocked_user_id: UserId):
        """ユーザーのブロックを解除"""
        # 自分自身をアンブロックしようとしていないかチェック
        if self._user_id == blocked_user_id:
            raise SelfUnblockException(int(self._user_id))

        if not self.is_blocked(blocked_user_id):
            raise CannotUnblockNotBlockedUserException(int(self._user_id), int(blocked_user_id))
        self._block_relationships = [block for block in self._block_relationships if block.blocked_user_id != blocked_user_id]
        event = SnsUserUnblockedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=self._user_id,
            blocked_user_id=blocked_user_id
        )
        self.add_event(event)

    def subscribe(self, subscribed_user_id: UserId):
        """ユーザーを購読"""
        # 自分自身を購読しようとしていないかチェック
        if self._user_id == subscribed_user_id:
            raise SelfSubscribeException(int(self._user_id))

        # フォロー関係があるかをチェック
        if not self.is_following(subscribed_user_id):
            raise CannotSubscribeNotFollowedUserException(int(self._user_id), int(subscribed_user_id))

        if self.is_subscribed(subscribed_user_id):
            raise CannotSubscribeAlreadySubscribedUserException(int(self._user_id), int(subscribed_user_id))
        self._subscribe_relationships.append(SubscribeRelationShip(subscriber_user_id=self._user_id, subscribed_user_id=subscribed_user_id))
        event = SnsUserSubscribedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=self._user_id,
            subscribed_user_id=subscribed_user_id
        )
        self.add_event(event)

    def unsubscribe(self, subscribed_user_id: UserId):
        """ユーザーの購読を解除"""
        # 自分自身をアンサブスクライブしようとしていないかチェック
        if self._user_id == subscribed_user_id:
            raise SelfUnsubscribeException(int(self._user_id))

        if not self.is_subscribed(subscribed_user_id):
            raise CannotUnsubscribeNotSubscribedUserException(int(self._user_id), int(subscribed_user_id))
        self._subscribe_relationships = [subscribe for subscribe in self._subscribe_relationships if subscribe.subscribed_user_id != subscribed_user_id]
        event = SnsUserUnsubscribedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=self._user_id,
            subscribed_user_id=subscribed_user_id
        )
        self.add_event(event)

    def is_following(self, user_id: UserId) -> bool:
        """指定したユーザーをフォローしているか"""
        return any(follow.followee_user_id == user_id for follow in self._follow_relationships)

    def is_blocked(self, user_id: UserId) -> bool:
        """指定したユーザーをブロックしているか"""
        return any(block.blocked_user_id == user_id for block in self._block_relationships)

    def is_subscribed(self, user_id: UserId) -> bool:
        """指定したユーザーを購読しているか"""
        return any(subscribe.subscribed_user_id == user_id for subscribe in self._subscribe_relationships)

    def relationship_between(self, user_id: UserId) -> dict:
        """指定したユーザーとの関係性を取得"""
        return {
            "is_following": self.is_following(user_id),
            "is_blocked": self.is_blocked(user_id),
            "is_subscribed": self.is_subscribed(user_id),
        }

    def get_user_profile_info(self) -> dict:
        """ユーザー基本情報を取得"""
        return {
            "user_id": int(self._user_id),
            "user_name": self._sns_user.user_profile.user_name,
            "display_name": self._sns_user.user_profile.display_name,
            "bio": self._sns_user.user_profile.bio,
        }

    def update_user_profile(self, new_bio: Optional[str], new_display_name: Optional[str]):
        """ユーザーのプロフィールを更新"""
        # 少なくとも1つのフィールドが指定されているかチェック
        if new_bio is None and new_display_name is None:
            raise ProfileUpdateValidationException()

        # 現在のプロフィールを取得
        current_profile = self._sns_user.user_profile

        # 新しいプロフィールを作成
        updated_profile = current_profile
        if new_bio is not None:
            updated_profile = updated_profile.update_bio(new_bio)
        if new_display_name is not None:
            updated_profile = updated_profile.update_display_name(new_display_name)

        # SnsUserを新しいプロフィールで更新
        self._sns_user = SnsUser(self._user_id, updated_profile)

        event = SnsUserProfileUpdatedEvent.create(
            aggregate_id=self._user_id,
            aggregate_type="UserAggregate",
            user_id=self._user_id,
            new_bio=new_bio,
            new_display_name=new_display_name
        )
        self.add_event(event)