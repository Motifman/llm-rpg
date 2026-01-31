"""
通知コマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.social.exceptions.base_exception import ApplicationException


class NotificationCommandException(ApplicationException):
    """通知コマンド関連の例外"""

    def __init__(self, message: str, error_code: str = None, user_id: Optional[int] = None, notification_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if user_id is not None:
            all_context['user_id'] = user_id
        if notification_id is not None:
            all_context['notification_id'] = notification_id
        super().__init__(message, error_code, **all_context)


class NotificationMarkAsReadException(NotificationCommandException):
    """通知既読化関連の例外"""

    def __init__(self, message: str, notification_id: Optional[int] = None, user_id: Optional[int] = None):
        super().__init__(message, "NOTIFICATION_MARK_AS_READ_ERROR", notification_id=notification_id, user_id=user_id)


class NotificationMarkAllAsReadException(NotificationCommandException):
    """通知一括既読化関連の例外"""

    def __init__(self, message: str, user_id: int):
        self.user_id = user_id
        super().__init__(message, "NOTIFICATION_MARK_ALL_AS_READ_ERROR", user_id=user_id)


class NotificationNotFoundForCommandException(NotificationCommandException):
    """コマンド実行時に通知が見つからない場合の例外"""

    def __init__(self, notification_id: int, command_name: str):
        self.notification_id = notification_id
        self.command_name = command_name
        message = f"コマンド '{command_name}' の実行時に通知が見つかりません: {notification_id}"
        super().__init__(message, "NOTIFICATION_NOT_FOUND_FOR_COMMAND", notification_id=notification_id)


class NotificationAccessDeniedException(NotificationCommandException):
    """通知アクセス権限がない場合の例外"""

    def __init__(self, notification_id: int, user_id: int, action: str):
        self.notification_id = notification_id
        self.user_id = user_id
        self.action = action
        message = f"通知 {notification_id} に対するアクション '{action}' の実行権限がありません: ユーザー {user_id}"
        super().__init__(message, "NOTIFICATION_ACCESS_DENIED", notification_id=notification_id, user_id=user_id)


class NotificationOwnershipException(NotificationCommandException):
    """通知所有権がない場合の例外"""

    def __init__(self, notification_id: int, user_id: int, action: str):
        self.notification_id = notification_id
        self.user_id = user_id
        self.action = action
        message = f"通知 {notification_id} の所有者でないためアクション '{action}' を実行できません: ユーザー {user_id}"
        super().__init__(message, "NOTIFICATION_OWNERSHIP_ERROR", notification_id=notification_id, user_id=user_id)
