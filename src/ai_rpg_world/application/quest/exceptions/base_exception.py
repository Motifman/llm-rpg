"""
クエストアプリケーション層の基底例外定義
"""

from typing import Optional, Any


class QuestApplicationException(Exception):
    """クエストアプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context):
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context
        super().__init__(message)
        self.user_id = context.get("user_id")
        self.quest_id = context.get("quest_id")


class QuestSystemErrorException(QuestApplicationException):
    """クエストシステムエラーの場合の例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context = {}
        if original_exception:
            context["original_exception"] = original_exception
        super().__init__(message, error_code="QUEST_SYSTEM_ERROR", **context)
        self.original_exception = original_exception
