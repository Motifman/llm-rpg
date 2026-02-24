"""会話アプリケーション層の基底例外"""
from typing import Optional, Any


class ConversationApplicationException(Exception):
    """会話アプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context):
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context
        super().__init__(message)


class ConversationSystemErrorException(ConversationApplicationException):
    """会話システムエラーの場合の例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context = {}
        if original_exception:
            context["original_exception"] = original_exception
        super().__init__(message, error_code="CONVERSATION_SYSTEM_ERROR", **context)
        self.original_exception = original_exception
