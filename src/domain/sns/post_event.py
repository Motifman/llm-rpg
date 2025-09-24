from dataclasses import dataclass, field
from datetime import datetime
from src.domain.sns.post_content import PostContent
from src.domain.common.domain_event import DomainEvent
from typing import Set
from src.domain.sns.mention import Mention


@dataclass(frozen=True)
class SnsPostCreatedEvent(DomainEvent):
    post_id: int = -1
    post_content: PostContent = field(default_factory=PostContent)
    mentions: Set[Mention] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsPostLikedEvent(DomainEvent):
    post_id: int = -1
    liked_user_id: int = -1
    author_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsPostDeletedEvent(DomainEvent):
    post_id: int = -1
    author_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SnsReplyDeletedEvent(DomainEvent):
    reply_id: int = -1
    author_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)