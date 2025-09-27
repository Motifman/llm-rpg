from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from src.domain.common.domain_event import BaseDomainEvent
from src.domain.sns.value_object import UserId

if TYPE_CHECKING:
    from src.domain.sns.aggregate import UserAggregate


@dataclass(frozen=True)
class SnsUserCreatedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """ユーザー作成イベント"""
    user_id: UserId
    user_name: str
    display_name: str
    bio: str


@dataclass(frozen=True)
class SnsUserFollowedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """フォローイベント"""
    follower_user_id: UserId
    followee_user_id: UserId


@dataclass(frozen=True)
class SnsUserUnfollowedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """フォロー解除イベント"""
    follower_user_id: UserId
    followee_user_id: UserId


@dataclass(frozen=True)
class SnsUserBlockedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """ブロックイベント"""
    blocker_user_id: UserId
    blocked_user_id: UserId


@dataclass(frozen=True)
class SnsUserUnblockedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """ブロック解除イベント"""
    blocker_user_id: UserId
    blocked_user_id: UserId


@dataclass(frozen=True)
class SnsUserProfileUpdatedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """プロフィール更新イベント"""
    user_id: UserId
    new_bio: Optional[str]
    new_display_name: Optional[str]


@dataclass(frozen=True)
class SnsUserSubscribedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """ユーザーサブスクライブイベント"""
    subscriber_user_id: UserId
    subscribed_user_id: UserId


@dataclass(frozen=True)
class SnsUserUnsubscribedEvent(BaseDomainEvent[UserId, "UserAggregate"]):
    """ユーザーアンサブスクライブイベント"""
    subscriber_user_id: UserId
    subscribed_user_id: UserId