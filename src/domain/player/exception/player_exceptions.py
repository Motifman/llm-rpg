"""
Playerドメインのプレイヤー関連例外
"""

from src.domain.player.exception.base_exceptions import PlayerDomainException


class PlayerIdValidationException(PlayerDomainException):
    """プレイヤーIDバリデーション例外"""
    error_code = "PLAYER_ID_VALIDATION_ERROR"

    def __init__(self, player_id, message: str = None):
        self.player_id = player_id
        if message is None:
            message = f"プレイヤーIDは正の数値である必要があります。入力値: {player_id}"
        super().__init__(message)


class HpValidationException(PlayerDomainException):
    """HPバリデーション例外"""
    error_code = "HP_VALIDATION_ERROR"

    def __init__(self, message: str):
        super().__init__(message)


class MpValidationException(PlayerDomainException):
    """MPバリデーション例外"""
    error_code = "MP_VALIDATION_ERROR"

    def __init__(self, message: str):
        super().__init__(message)


class BaseStatusValidationException(PlayerDomainException):
    """基礎ステータスバリデーション例外"""
    error_code = "BASE_STATUS_VALIDATION_ERROR"

    def __init__(self, message: str):
        super().__init__(message)


class MessageValidationException(PlayerDomainException):
    """メッセージバリデーション例外"""
    error_code = "MESSAGE_VALIDATION_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
