"""
アプリケーション層のSNS例外
"""

# 例外ファクトリ
from ai_rpg_world.application.social.exceptions.exception_factory import ApplicationExceptionFactory

# 基底例外
from ai_rpg_world.application.social.exceptions.base_exception import ApplicationException, SystemErrorException

# クエリ関連例外
from ai_rpg_world.application.social.exceptions.query.user_query_exception import (
    UserQueryException,
    ProfileNotFoundException,
    UserNotFoundException,
    InvalidUserIdException,
    RelationshipQueryException,
)
from ai_rpg_world.application.social.exceptions.query.notification_query_exception import (
    NotificationQueryException,
    NotificationNotFoundException,
    NotificationAccessDeniedException,
    InvalidNotificationIdException,
    NotificationQueryAccessException,
)
# RelationshipQueryException is now imported from user_query_exception

# コマンド関連例外
from ai_rpg_world.application.social.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
)
from ai_rpg_world.application.social.exceptions.command.relationship_command_exception import (
    UserFollowException,
    UserBlockException,
    UserSubscribeException,
)
from ai_rpg_world.application.social.exceptions.command.notification_command_exception import (
    NotificationCommandException,
    NotificationMarkAsReadException,
    NotificationMarkAllAsReadException,
    NotificationNotFoundForCommandException,
    NotificationAccessDeniedException,
    NotificationOwnershipException,
)

__all__ = [
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
    "NotificationAccessDeniedException",
    "NotificationOwnershipException",
]
