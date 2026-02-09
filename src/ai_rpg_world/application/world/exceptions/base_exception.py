from typing import Optional
from ai_rpg_world.application.common.exceptions import ApplicationException


class WorldApplicationException(ApplicationException):
    """ワールドドメインのアプリケーション例外基底クラス"""
    
    def __init__(self, message: str, error_code: str = None, **context):
        super().__init__(message, **context)
        self.error_code = error_code


class WorldSystemErrorException(WorldApplicationException):
    """ワールドドメインのシステム例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message, "SYSTEM_ERROR", original_exception=original_exception)
        self.original_exception = original_exception
