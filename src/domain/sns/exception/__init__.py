"""
SNSドメインの例外クラス

このパッケージからすべての例外クラスをインポートできます。
"""

# 基底例外
from src.domain.sns.exception.base_exceptions import (
    SnsDomainException,
    UserProfileException,
    UserRelationshipException,
    ContentValidationException,
    ContentTypeException,
)

# 所有権関連例外
from src.domain.sns.exception.content_exceptions import (
    OwnershipException,
)

# ユーザープロファイル関連例外
from src.domain.sns.exception.user_profile_exceptions import (
    UserNotFoundException,
    UserIdValidationException,
    UserNameValidationException,
    DisplayNameValidationException,
    BioValidationException,
    ProfileUpdateValidationException,
)

# 関係性関連例外
from src.domain.sns.exception.relationship_exceptions import (
    FollowException,
    CannotFollowBlockedUserException,
    CannotUnfollowNotFollowedUserException,
    BlockException,
    CannotBlockAlreadyBlockedUserException,
    CannotUnblockNotBlockedUserException,
    SubscribeException,
    CannotSubscribeAlreadySubscribedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    CannotUnsubscribeNotSubscribedUserException,
    RelationshipValidationException,
    PositiveUserIdValidationException,
    SelfReferenceValidationException,
    SelfFollowException,
    SelfUnfollowException,
    SelfBlockException,
    SelfUnblockException,
    SelfSubscribeException,
    SelfUnsubscribeException,
)

# コンテンツ関連例外
from src.domain.sns.exception.content_exceptions import (
    InvalidContentTypeException,
    InvalidParentReferenceException,
    PostIdValidationException,
    ReplyIdValidationException,
    NotificationIdValidationException,
    NotificationContentValidationException,
    ContentLengthValidationException,
    HashtagCountValidationException,
    VisibilityValidationException,
    MentionValidationException,
    ContentOwnershipException,
    ContentTypeMismatchException,
    ContentAlreadyDeletedException,
)


__all__ = [
    # 基底例外
    "SnsDomainException",
    "UserProfileException",
    "UserRelationshipException",
    "ContentValidationException",
    "ContentTypeException",
    "OwnershipException",

    # ユーザープロファイル関連例外
    "UserNotFoundException",
    "UserIdValidationException",
    "UserNameValidationException",
    "DisplayNameValidationException",
    "BioValidationException",
    "ProfileUpdateValidationException",

    # 関係性関連例外
    "FollowException",
    "CannotFollowBlockedUserException",
    "CannotUnfollowNotFollowedUserException",
    "BlockException",
    "CannotBlockAlreadyBlockedUserException",
    "CannotUnblockNotBlockedUserException",
    "SubscribeException",
    "CannotSubscribeAlreadySubscribedUserException",
    "CannotSubscribeBlockedUserException",
    "CannotSubscribeNotFollowedUserException",
    "CannotUnsubscribeNotSubscribedUserException",
    "RelationshipValidationException",
    "PositiveUserIdValidationException",
    "SelfReferenceValidationException",
    "SelfFollowException",
    "SelfUnfollowException",
    "SelfBlockException",
    "SelfUnblockException",
    "SelfSubscribeException",
    "SelfUnsubscribeException",

    # コンテンツ関連例外
    "InvalidContentTypeException",
    "InvalidParentReferenceException",
    "PostIdValidationException",
    "ReplyIdValidationException",
    "NotificationIdValidationException",
    "NotificationContentValidationException",
    "ContentLengthValidationException",
    "HashtagCountValidationException",
    "VisibilityValidationException",
    "MentionValidationException",
    "ContentOwnershipException",
    "ContentTypeMismatchException",
    "ContentAlreadyDeletedException",
    "OwnershipException",
]
