"""
ポスト検索関連の例外定義
"""

from typing import Optional
from src.application.sns.exceptions.base_exception import ApplicationException


class PostQueryException(ApplicationException):
    """ポスト検索関連の例外"""

    def __init__(self, message: str, error_code: str = None, post_id: Optional[int] = None, user_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if post_id is not None:
            all_context['post_id'] = post_id
        if user_id is not None:
            all_context['user_id'] = user_id
        super().__init__(message, error_code, **all_context)


class PostNotFoundException(PostQueryException):
    """ポストが見つからない場合の例外"""

    def __init__(self, post_id: int):
        message = f"ポストが見つかりません: {post_id}"
        super().__init__(message, "POST_NOT_FOUND", post_id=post_id)


class PostAccessDeniedException(PostQueryException):
    """ポストへのアクセス権限がない場合の例外"""

    def __init__(self, post_id: int, user_id: int):
        message = f"ポストへのアクセス権限がありません。post_id: {post_id}, user_id: {user_id}"
        super().__init__(message, "POST_ACCESS_DENIED", post_id=post_id, user_id=user_id)


class InvalidPostIdException(PostQueryException):
    """無効なポストIDの場合の例外"""

    def __init__(self, post_id: int):
        message = f"無効なポストIDです: {post_id}"
        super().__init__(message, "INVALID_POST_ID", post_id=post_id)


class PostQueryAccessException(PostQueryException):
    """ポスト検索関連のアクセス例外"""

    def __init__(self, message: str, post_id: Optional[int] = None, user_id: Optional[int] = None):
        super().__init__(message, "POST_QUERY_ACCESS_ERROR", post_id=post_id, user_id=user_id)
