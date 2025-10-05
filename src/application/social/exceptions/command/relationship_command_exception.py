"""
関係性コマンド関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.command.user_command_exception import UserCommandException


class UserFollowException(UserCommandException):
    """ユーザーフォロー関連の例外"""

    def __init__(self, message: str, follower_user_id: int, followee_user_id: int):
        self.follower_user_id = follower_user_id
        self.followee_user_id = followee_user_id
        super().__init__(message, "USER_FOLLOW_ERROR", user_id=follower_user_id, target_user_id=followee_user_id)


class UserBlockException(UserCommandException):
    """ユーザーブロック関連の例外"""

    def __init__(self, message: str, blocker_user_id: int, blocked_user_id: int):
        self.blocker_user_id = blocker_user_id
        self.blocked_user_id = blocked_user_id
        super().__init__(message, "USER_BLOCK_ERROR", user_id=blocker_user_id, target_user_id=blocked_user_id)


class UserSubscribeException(UserCommandException):
    """ユーザー購読関連の例外"""

    def __init__(self, message: str, subscriber_user_id: int, subscribed_user_id: int):
        self.subscriber_user_id = subscriber_user_id
        self.subscribed_user_id = subscribed_user_id
        super().__init__(message, "USER_SUBSCRIBE_ERROR", user_id=subscriber_user_id, target_user_id=subscribed_user_id)
