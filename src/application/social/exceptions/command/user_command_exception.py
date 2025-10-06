"""
ユーザーコマンド関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.base_exception import ApplicationException


class UserCommandException(ApplicationException):
    """ユーザーコマンド関連の例外"""

    def __init__(self, message: str, error_code: str = None, user_id: Optional[int] = None, target_user_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if user_id is not None:
            all_context['user_id'] = user_id
        if target_user_id is not None:
            all_context['target_user_id'] = target_user_id
        super().__init__(message, error_code, **all_context)


class UserCreationException(UserCommandException):
    """ユーザー作成関連の例外"""

    def __init__(self, message: str, user_name: str):
        self.user_name = user_name
        super().__init__(message, "USER_CREATION_ERROR", user_name=user_name)


class UserProfileUpdateException(UserCommandException):
    """ユーザープロフィール更新関連の例外"""

    def __init__(self, message: str, user_id: int):
        super().__init__(message, "USER_PROFILE_UPDATE_ERROR", user_id=user_id)


class UserNotFoundForCommandException(UserCommandException):
    """コマンド実行時にユーザーが見つからない場合の例外"""

    def __init__(self, user_id: int, command_name: str):
        self.user_id = user_id
        self.command_name = command_name
        message = f"コマンド '{command_name}' の実行時にユーザーが見つかりません: {user_id}"
        super().__init__(message, "USER_NOT_FOUND_FOR_COMMAND", user_id=user_id)
