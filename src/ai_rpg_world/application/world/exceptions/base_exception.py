from typing import Any

from ai_rpg_world.application.common.exceptions import ApplicationException


class WorldApplicationException(ApplicationException):
    """ワールドドメインのアプリケーション例外基底クラス"""

    def __init__(self, message: str, error_code: str | None = None, **context: Any) -> None:
        super().__init__(message, **context)
        self.error_code = error_code
