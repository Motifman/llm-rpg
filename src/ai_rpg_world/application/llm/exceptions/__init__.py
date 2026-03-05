"""LLM 向け表示・記憶層の例外"""

from typing import Optional

from ai_rpg_world.application.common.exceptions import ApplicationException


class LlmApplicationException(ApplicationException):
    """LLM 表示・記憶層のアプリケーション例外基底"""

    def __init__(self, message: str, error_code: str = "LLM_ERROR", **context):
        super().__init__(message, **context)
        self.error_code = error_code


class PlayerProfileNotFoundForPromptException(LlmApplicationException):
    """プロンプト組み立て時にプレイヤープロフィールが見つからない場合"""

    def __init__(self, player_id: int):
        super().__init__(
            f"Player profile not found for player_id={player_id}. Cannot build system prompt.",
            error_code="PLAYER_PROFILE_NOT_FOUND",
            player_id=player_id,
        )
        self.player_id = player_id


class LlmApiCallException(LlmApplicationException):
    """LLM API 呼び出し（LiteLLM 等）が失敗した場合"""

    def __init__(self, message: str, error_code: str = "LLM_API_CALL_FAILED", cause: Optional[Exception] = None, **context):
        super().__init__(message, cause=cause, error_code=error_code, **context)
        self.cause = cause
