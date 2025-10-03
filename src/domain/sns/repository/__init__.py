"""
SNSドメインのリポジトリインターフェース

リポジトリはドメイン層とインフラ層の境界を定義します。
"""

from .post_repository import PostRepository
from .reply_repository import ReplyRepository
from .sns_user_repository import UserRepository
from .sns_notification_repository import SnsNotificationRepository

__all__ = [
    "PostRepository",
    "ReplyRepository",
    "SnsNotificationRepository",
    "UserRepository",
]
