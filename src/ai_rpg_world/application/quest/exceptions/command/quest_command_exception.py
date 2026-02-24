"""
クエストコマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.quest.exceptions.base_exception import QuestApplicationException


class QuestCommandException(QuestApplicationException):
    """クエストコマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str = None,
        user_id: Optional[int] = None,
        quest_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if user_id is not None:
            all_context["user_id"] = user_id
        if quest_id is not None:
            all_context["quest_id"] = quest_id
        super().__init__(message, error_code, **all_context)


class QuestCreationException(QuestCommandException):
    """クエスト作成関連の例外"""

    def __init__(self, message: str, user_id: Optional[int] = None):
        super().__init__(message, "QUEST_CREATION_ERROR", user_id=user_id)


class QuestNotFoundForCommandException(QuestCommandException):
    """コマンド実行時にクエストが見つからない場合の例外"""

    def __init__(self, quest_id: int, command_name: str):
        message = f"コマンド '{command_name}' の実行時にクエストが見つかりません: {quest_id}"
        super().__init__(message, "QUEST_NOT_FOUND_FOR_COMMAND", quest_id=quest_id)


class QuestAccessDeniedException(QuestCommandException):
    """クエストに対するアクション権限がない場合の例外"""

    def __init__(self, quest_id: int, user_id: int, action: str):
        message = f"クエスト {quest_id} に対するアクション '{action}' の実行権限がありません: ユーザー {user_id}"
        super().__init__(message, "QUEST_ACCESS_DENIED", quest_id=quest_id, user_id=user_id)
