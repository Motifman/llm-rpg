from dataclasses import dataclass, field
from datetime import datetime
from src.domain.common.domain_event import DomainEvent


@dataclass(frozen=True)
class SnsUserFollowedEvent(DomainEvent):
    """フォローイベント"""
    follower_user_id: int = 0
    followee_user_id: int = 0
    follow_time: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.follower_user_id <= 0:
            raise ValueError("follower_user_id must be positive")
        if self.followee_user_id <= 0:
            raise ValueError("followee_user_id must be positive")


@dataclass(frozen=True)
class SnsUserUnfollowedEvent(DomainEvent):
    """フォロー解除イベント"""
    follower_user_id: int = 0
    followee_user_id: int = 0
    unfollow_time: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.follower_user_id <= 0:
            raise ValueError("follower_user_id must be positive")
        if self.followee_user_id <= 0:
            raise ValueError("followee_user_id must be positive")


@dataclass(frozen=True)
class SnsUserBlockedEvent(DomainEvent):
    """ブロックイベント"""
    blocker_user_id: int = 0
    blocked_user_id: int = 0
    block_time: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.blocker_user_id <= 0:
            raise ValueError("blocker_user_id must be positive")
        if self.blocked_user_id <= 0:
            raise ValueError("blocked_user_id must be positive")


@dataclass(frozen=True)
class SnsUserUnblockedEvent(DomainEvent):
    """ブロック解除イベント"""
    blocker_user_id: int = 0
    blocked_user_id: int = 0
    unblock_time: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.blocker_user_id <= 0:
            raise ValueError("blocker_user_id must be positive")
        if self.blocked_user_id <= 0:
            raise ValueError("blocked_user_id must be positive")


@dataclass(frozen=True)
class SnsUserProfileUpdatedEvent(DomainEvent):
    """プロフィール更新イベント"""
    user_id: int = 0
    new_bio: str = ""
    new_display_name: str = ""
    updated_time: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")
        if len(self.new_bio) > 200:
            raise ValueError("new_bio must be less than 200 characters")
        if len(self.new_display_name) > 30:
            raise ValueError("new_display_name must be less than 30 characters")