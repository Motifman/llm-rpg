"""SNSドメインイベントパッケージ"""

from .post_event import (
    SnsContentDeletedEvent,
    SnsContentLikedEvent,
    SnsContentMentionedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
)
from .sns_user_event import (
    SnsUserBlockedEvent,
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnblockedEvent,
    SnsUserUnfollowedEvent,
    SnsUserUnsubscribedEvent,
)

__all__ = [
    # Post events
    "SnsPostCreatedEvent",
    "SnsReplyCreatedEvent",
    "SnsContentLikedEvent",
    "SnsContentDeletedEvent",
    "SnsContentMentionedEvent",
    # User events
    "SnsUserCreatedEvent",
    "SnsUserFollowedEvent",
    "SnsUserUnfollowedEvent",
    "SnsUserBlockedEvent",
    "SnsUserUnblockedEvent",
    "SnsUserProfileUpdatedEvent",
    "SnsUserSubscribedEvent",
    "SnsUserUnsubscribedEvent",
]
