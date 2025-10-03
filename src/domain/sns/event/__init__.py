"""SNSドメインイベントパッケージ"""

from .post_event import (
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
    SnsContentDeletedEvent,
    SnsContentMentionedEvent,
)

from .sns_user_event import (
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserUnfollowedEvent,
    SnsUserBlockedEvent,
    SnsUserUnblockedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
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
