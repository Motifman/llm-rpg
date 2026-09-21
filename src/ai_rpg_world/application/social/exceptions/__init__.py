"""
アプリケーション層のSNS例外
"""

# 例外ファクトリ
# 基底例外
from ai_rpg_world.application.social.exceptions.base_exception import ApplicationException, SystemErrorException
from ai_rpg_world.application.social.exceptions.command.notification_command_exception import (
    NotificationAccessDeniedForCommandException,
    NotificationCommandException,
    NotificationMarkAllAsReadException,
    NotificationMarkAsReadException,
    NotificationNotFoundForCommandException,
    NotificationOwnershipException,
)
from ai_rpg_world.application.social.exceptions.command.relationship_command_exception import (
    UserBlockException,
    UserFollowException,
    UserSubscribeException,
)

# RelationshipQueryException is now imported from user_query_exception
# コマンド関連例外
from ai_rpg_world.application.social.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
)
from ai_rpg_world.application.social.exceptions.exception_factory import ApplicationExceptionFactory
from ai_rpg_world.application.social.exceptions.query.notification_query_exception import (
    InvalidNotificationIdException,
    NotificationAccessDeniedException,
    NotificationNotFoundException,
    NotificationQueryAccessException,
    NotificationQueryException,
)

# クエリ関連例外
from ai_rpg_world.application.social.exceptions.query.user_query_exception import (
    InvalidUserIdException,
    ProfileNotFoundException,
    RelationshipQueryException,
    UserNotFoundException,
    UserQueryException,
)

__all__ = [
    # 例外ファクトリ
    "ApplicationExceptionFactory",
    # 基底例外
    "ApplicationException",
    "SystemErrorException",
    # クエリ関連例外
    "UserQueryException",
    "ProfileNotFoundException",
    "UserNotFoundException",
    "InvalidUserIdException",
    "RelationshipQueryException",
    "NotificationQueryException",
    "NotificationNotFoundException",
    "NotificationAccessDeniedException",
    "InvalidNotificationIdException",
    "NotificationQueryAccessException",
    # コマンド関連例外
    "UserCommandException",
    "UserCreationException",
    "UserProfileUpdateException",
    "UserFollowException",
    "UserBlockException",
    "UserSubscribeException",
    "NotificationCommandException",
    "NotificationMarkAsReadException",
    "NotificationMarkAllAsReadException",
    "NotificationNotFoundForCommandException",
    "NotificationAccessDeniedForCommandException",
    "NotificationOwnershipException",
]
