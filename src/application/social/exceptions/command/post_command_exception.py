"""
ポストコマンド関連の例外定義
"""

from typing import Optional
from src.application.social.exceptions.base_exception import ApplicationException


class PostCommandException(ApplicationException):
    """ポストコマンド関連の例外"""

    def __init__(self, message: str, error_code: str = None, user_id: Optional[int] = None, post_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if user_id is not None:
            all_context['user_id'] = user_id
        if post_id is not None:
            all_context['post_id'] = post_id
        super().__init__(message, error_code, **all_context)


class PostCreationException(PostCommandException):
    """ポスト作成関連の例外"""

    def __init__(self, message: str, user_id: int):
        self.user_id = user_id
        super().__init__(message, "POST_CREATION_ERROR", user_id=user_id)


class PostDeletionException(PostCommandException):
    """ポスト削除関連の例外"""

    def __init__(self, message: str, post_id: int, user_id: int):
        self.post_id = post_id
        self.user_id = user_id
        super().__init__(message, "POST_DELETION_ERROR", post_id=post_id, user_id=user_id)


class PostLikeException(PostCommandException):
    """ポストいいね関連の例外"""

    def __init__(self, message: str, post_id: int, user_id: int):
        self.post_id = post_id
        self.user_id = user_id
        super().__init__(message, "POST_LIKE_ERROR", post_id=post_id, user_id=user_id)


class PostNotFoundForCommandException(PostCommandException):
    """コマンド実行時にポストが見つからない場合の例外"""

    def __init__(self, post_id: int, command_name: str):
        self.post_id = post_id
        self.command_name = command_name
        message = f"コマンド '{command_name}' の実行時にポストが見つかりません: {post_id}"
        super().__init__(message, "POST_NOT_FOUND_FOR_COMMAND", post_id=post_id)


class PostAccessDeniedException(PostCommandException):
    """ポストアクセス権限がない場合の例外"""

    def __init__(self, post_id: int, user_id: int, action: str):
        self.post_id = post_id
        self.user_id = user_id
        self.action = action
        message = f"ポスト {post_id} に対するアクション '{action}' の実行権限がありません: ユーザー {user_id}"
        super().__init__(message, "POST_ACCESS_DENIED", post_id=post_id, user_id=user_id)


class PostOwnershipException(PostCommandException):
    """ポスト所有権がない場合の例外"""

    def __init__(self, post_id: int, user_id: int, action: str):
        self.post_id = post_id
        self.user_id = user_id
        self.action = action
        message = f"ポスト {post_id} の所有者でないためアクション '{action}' を実行できません: ユーザー {user_id}"
        super().__init__(message, "POST_OWNERSHIP_ERROR", post_id=post_id, user_id=user_id)
