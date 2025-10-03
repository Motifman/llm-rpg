"""
アプリケーション層のSNS例外
"""

# 例外ファクトリ
from src.application.sns.exceptions.exception_factory import ApplicationExceptionFactory

# 基底例外
from src.application.sns.exceptions.base_exception import ApplicationException, SystemErrorException

# クエリ関連例外
from src.application.sns.exceptions.query.user_query_exception import (
    UserQueryException,
    ProfileNotFoundException,
    UserNotFoundException,
    InvalidUserIdException,
    RelationshipQueryException,
)
from src.application.sns.exceptions.query.notification_query_exception import (
    NotificationQueryException,
    NotificationNotFoundException,
    NotificationAccessDeniedException,
    InvalidNotificationIdException,
    NotificationQueryAccessException,
)
# RelationshipQueryException is now imported from user_query_exception

# コマンド関連例外
from src.application.sns.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
)
from src.application.sns.exceptions.command.relationship_command_exception import (
    UserFollowException,
    UserBlockException,
    UserSubscribeException,
)
from src.application.sns.exceptions.command.notification_command_exception import (
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
