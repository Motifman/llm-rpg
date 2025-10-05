"""
ユーザー検索関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.base_exception import ApplicationException


class UserQueryException(ApplicationException):
    """ユーザー検索関連の例外"""

    def __init__(self, message: str, error_code: str = None, user_id: Optional[int] = None, target_user_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if user_id is not None:
            all_context['user_id'] = user_id
        if target_user_id is not None:
            all_context['target_user_id'] = target_user_id
        super().__init__(message, error_code, **all_context)


class ProfileNotFoundException(UserQueryException):
    """プロフィールが見つからない場合の例外"""

    def __init__(self, user_id: int):
        message = f"ユーザープロフィールが見つかりません: {user_id}"
        super().__init__(message, "PROFILE_NOT_FOUND", user_id=user_id)


class UserNotFoundException(UserQueryException):
    """ユーザーが見つからない場合の例外"""

    def __init__(self, user_id: int):
        message = f"ユーザーが見つかりません: {user_id}"
        super().__init__(message, "USER_NOT_FOUND", user_id=user_id)


class InvalidUserIdException(UserQueryException):
    """無効なユーザーIDの場合の例外"""

    def __init__(self, user_id: int):
        message = f"無効なユーザーIDです: {user_id}"
        super().__init__(message, "INVALID_USER_ID", user_id=user_id)


class ProfileQueryException(UserQueryException):
    """プロフィール検索関連の例外"""

    def __init__(self, message: str, user_id: Optional[int] = None, target_user_id: Optional[int] = None):
        super().__init__(message, "PROFILE_QUERY_ERROR", user_id=user_id, target_user_id=target_user_id)


class RelationshipQueryException(UserQueryException):
    """関係性検索関連の例外"""

    def __init__(self, message: str, relationship_type: str, user_id: int):
        self.relationship_type = relationship_type
        super().__init__(message, "RELATIONSHIP_QUERY_ERROR", user_id=user_id)
