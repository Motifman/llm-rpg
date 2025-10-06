"""
リプライコマンド関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.base_exception import ApplicationException


class ReplyCommandException(ApplicationException):
    """リプライコマンド関連の例外"""

    def __init__(self, message: str, error_code: str = None, user_id: Optional[int] = None, reply_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if user_id is not None:
            all_context['user_id'] = user_id
        if reply_id is not None:
            all_context['reply_id'] = reply_id
        super().__init__(message, error_code, **all_context)


class ReplyCreationException(ReplyCommandException):
    """リプライ作成関連の例外"""

    def __init__(self, message: str, user_id: int, parent_post_id: Optional[int] = None, parent_reply_id: Optional[int] = None):
        self.parent_post_id = parent_post_id
        self.parent_reply_id = parent_reply_id
        super().__init__(message, "REPLY_CREATION_ERROR", user_id=user_id)


class ReplyDeletionException(ReplyCommandException):
    """リプライ削除関連の例外"""

    def __init__(self, message: str, reply_id: int, user_id: int):
        self.reply_id = reply_id
        self.user_id = user_id
        super().__init__(message, "REPLY_DELETION_ERROR", reply_id=reply_id, user_id=user_id)


class ReplyLikeException(ReplyCommandException):
    """リプライいいね関連の例外"""

    def __init__(self, message: str, reply_id: int, user_id: int):
        self.reply_id = reply_id
        self.user_id = user_id
        super().__init__(message, "REPLY_LIKE_ERROR", reply_id=reply_id, user_id=user_id)


class ReplyNotFoundForCommandException(ReplyCommandException):
    """コマンド実行時にリプライが見つからない場合の例外"""

    def __init__(self, reply_id: int, command_name: str):
        self.reply_id = reply_id
        self.command_name = command_name
        message = f"コマンド '{command_name}' の実行時にリプライが見つかりません: {reply_id}"
        super().__init__(message, "REPLY_NOT_FOUND_FOR_COMMAND", reply_id=reply_id)


class ReplyAccessDeniedException(ReplyCommandException):
    """リプライアクセス権限がない場合の例外"""

    def __init__(self, reply_id: int, user_id: int, action: str):
        self.reply_id = reply_id
        self.user_id = user_id
        self.action = action
        message = f"リプライ {reply_id} に対するアクション '{action}' の実行権限がありません: ユーザー {user_id}"
        super().__init__(message, "REPLY_ACCESS_DENIED", reply_id=reply_id, user_id=user_id)


class ReplyOwnershipException(ReplyCommandException):
    """リプライ所有権がない場合の例外"""

    def __init__(self, message: str, reply_id: int, user_id: int, action: str):
        self.reply_id = reply_id
        self.user_id = user_id
        self.action = action
        super().__init__(message, "REPLY_OWNERSHIP_ERROR", reply_id=reply_id, user_id=user_id)
