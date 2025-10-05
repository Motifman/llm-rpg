"""
リプライ検索関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.base_exception import ApplicationException


class ReplyQueryException(ApplicationException):
    """リプライ検索関連の例外"""

    def __init__(self, message: str, error_code: str = None, reply_id: Optional[int] = None, post_id: Optional[int] = None, user_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if reply_id is not None:
            all_context['reply_id'] = reply_id
        if post_id is not None:
            all_context['post_id'] = post_id
        if user_id is not None:
            all_context['user_id'] = user_id
        super().__init__(message, error_code, **all_context)


class ReplyNotFoundException(ReplyQueryException):
    """リプライが見つからない場合の例外"""

    def __init__(self, reply_id: int, message: Optional[str] = None):
        if message is None:
            message = f"リプライが見つかりません: {reply_id}"
        super().__init__(message, "REPLY_NOT_FOUND", reply_id=reply_id)


class ReplyAccessDeniedException(ReplyQueryException):
    """リプライへのアクセス権限がない場合の例外"""

    def __init__(self, reply_id: int, user_id: int, reason: Optional[str] = None):
        if reason:
            message = f"リプライへのアクセス権限がありません。reply_id: {reply_id}, user_id: {user_id}, reason: {reason}"
        else:
            message = f"リプライへのアクセス権限がありません。reply_id: {reply_id}, user_id: {user_id}"
        super().__init__(message, "REPLY_ACCESS_DENIED", reply_id=reply_id, user_id=user_id)


class InvalidReplyIdException(ReplyQueryException):
    """無効なリプライIDの場合の例外"""

    def __init__(self, reply_id: int):
        message = f"無効なリプライIDです: {reply_id}"
        super().__init__(message, "INVALID_REPLY_ID", reply_id=reply_id)


class ReplyQueryAccessException(ReplyQueryException):
    """リプライ検索関連のアクセス例外"""

    def __init__(self, message: str, reply_id: Optional[int] = None, post_id: Optional[int] = None, user_id: Optional[int] = None):
        super().__init__(message, "REPLY_QUERY_ACCESS_ERROR", reply_id=reply_id, post_id=post_id, user_id=user_id)
