"""
通知検索関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.base_exception import ApplicationException


class NotificationQueryException(ApplicationException):
    """通知検索関連の例外"""

    def __init__(self, message: str, error_code: str = None, notification_id: Optional[int] = None, user_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if notification_id is not None:
            all_context['notification_id'] = notification_id
        if user_id is not None:
            all_context['user_id'] = user_id
        super().__init__(message, error_code, **all_context)


class NotificationNotFoundException(NotificationQueryException):
    """通知が見つからない場合の例外"""

    def __init__(self, notification_id: int):
        message = f"通知が見つかりません: {notification_id}"
        super().__init__(message, "NOTIFICATION_NOT_FOUND", notification_id=notification_id)


class NotificationAccessDeniedException(NotificationQueryException):
    """通知へのアクセス権限がない場合の例外"""

    def __init__(self, notification_id: int, user_id: int):
        message = f"通知へのアクセス権限がありません。notification_id: {notification_id}, user_id: {user_id}"
        super().__init__(message, "NOTIFICATION_ACCESS_DENIED", notification_id=notification_id, user_id=user_id)


class InvalidNotificationIdException(NotificationQueryException):
    """無効な通知IDの場合の例外"""

    def __init__(self, notification_id: int):
        message = f"無効な通知IDです: {notification_id}"
        super().__init__(message, "INVALID_NOTIFICATION_ID", notification_id=notification_id)


class NotificationQueryAccessException(NotificationQueryException):
    """通知検索関連のアクセス例外"""

    def __init__(self, message: str, notification_id: Optional[int] = None, user_id: Optional[int] = None):
        super().__init__(message, "NOTIFICATION_QUERY_ACCESS_ERROR", notification_id=notification_id, user_id=user_id)
