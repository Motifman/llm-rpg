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
    # コマンド関連例外
    "UserCommandException",
    "UserCreationException",
    "UserProfileUpdateException",
    "UserFollowException",
    "UserBlockException",
    "UserSubscribeException",
]
