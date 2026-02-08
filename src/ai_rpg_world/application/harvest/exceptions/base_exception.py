"""
採集アプリケーション層の基底例外定義
"""

from typing import Optional, Any, Dict


class HarvestApplicationException(Exception):
    """採集アプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context):
        """
        Args:
            message: エラーメッセージ
            error_code: エラーコード
            **context: 任意のコンテキスト情報
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context
        super().__init__(message)

        self.actor_id = context.get('actor_id')
        self.target_id = context.get('target_id')
        self.spot_id = context.get('spot_id')


class HarvestSystemErrorException(HarvestApplicationException):
    """採集システムエラーの場合の例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context = {}
        if original_exception:
            context['original_exception'] = original_exception
        super().__init__(message, error_code="HARVEST_SYSTEM_ERROR", **context)
        self.original_exception = original_exception
