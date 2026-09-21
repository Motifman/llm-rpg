"""
SNSドメインの例外クラス

このパッケージからすべての例外クラスをインポートできます。
"""

# 基底例外
from ai_rpg_world.domain.sns.exception.base_exceptions import (
    ContentTypeException,
    ContentValidationException,
    SnsDomainException,
    UserProfileException,
    UserRelationshipException,
)

# 所有権関連例外
# コンテンツ関連例外
from ai_rpg_world.domain.sns.exception.content_exceptions import (
    ContentAlreadyDeletedException,
    ContentLengthValidationException,
    ContentOwnershipException,
    ContentTypeMismatchException,
    HashtagCountValidationException,
    InvalidContentTypeException,
    InvalidParentReferenceException,
    MentionValidationException,
    NotificationContentValidationException,
    NotificationIdValidationException,
    OwnershipException,
    PostIdValidationException,
    ReplyIdValidationException,
    VisibilityValidationException,
)

# 関係性関連例外
from ai_rpg_world.domain.sns.exception.relationship_exceptions import (
    BlockException,
    CannotBlockAlreadyBlockedUserException,
    CannotFollowBlockedUserException,
    CannotSubscribeAlreadySubscribedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    CannotUnblockNotBlockedUserException,
    CannotUnfollowNotFollowedUserException,
    CannotUnsubscribeNotSubscribedUserException,
    FollowException,
    PositiveUserIdValidationException,
    RelationshipValidationException,
    SelfBlockException,
    SelfFollowException,
    SelfReferenceValidationException,
    SelfSubscribeException,
    SelfUnblockException,
    SelfUnfollowException,
    SelfUnsubscribeException,
    SubscribeException,
)

# ユーザープロファイル関連例外
from ai_rpg_world.domain.sns.exception.user_profile_exceptions import (
    BioValidationException,
    DisplayNameValidationException,
    ProfileUpdateValidationException,
    UserIdValidationException,
    UserNameValidationException,
    UserNotFoundException,
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
]
