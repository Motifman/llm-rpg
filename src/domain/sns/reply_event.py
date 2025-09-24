from dataclasses import dataclass, field
from datetime import datetime
from src.domain.common.domain_event import DomainEvent
from typing import Set
from src.domain.sns.mention import Mention


@dataclass(frozen=True)
class SnsReplyCreatedEvent(DomainEvent):
    reply_id: int = -1
    parent_post_id: int = -1
    parent_reply_id: int = -1
    author_user_id: int = -1
    content: str = ""
    likes: Set[int] = field(default_factory=set)
    mentions: Set[Mention] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsReplyLikedEvent(DomainEvent):
    reply_id: int = -1
    user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsReplyDeletedEvent(DomainEvent):
    reply_id: int = -1
    author_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsPostMentionedEvent(DomainEvent):
    post_id: int = -1
    mentioned_user_names: Set[str] = field(default_factory=set)
    mentioned_by_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsUserFollowedEvent(DomainEvent):
    follower_user_id: int = -1
    followed_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsUserBlockedEvent(DomainEvent):
    blocker_user_id: int = -1
    blocked_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsUserSubscribedEvent(DomainEvent):
    subscriber_user_id: int = -1
    subscribed_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)
