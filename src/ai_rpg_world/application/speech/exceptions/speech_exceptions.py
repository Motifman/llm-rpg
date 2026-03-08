"""プレイヤー間発言のアプリケーション例外"""

from typing import Optional


class SpeechApplicationException(Exception):
    """発言アプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context):
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context
        super().__init__(message)


class SpeechCommandException(SpeechApplicationException):
    """発言コマンドのバリデーション・ビジネスルール違反"""

    pass


class SpeechSystemErrorException(SpeechApplicationException):
    """発言処理のシステムエラー"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context = {}
        if original_exception is not None:
            context["original_exception"] = original_exception
        super().__init__(message, error_code="SPEECH_SYSTEM_ERROR", **context)
        self.original_exception = original_exception


class PlayerNotFoundException(SpeechCommandException):
    """発言者プレイヤーが存在しない"""

    def __init__(self, player_id: int):
        super().__init__(f"プレイヤーが見つかりません: player_id={player_id}", player_id=player_id)


class PlayerLocationNotSetException(SpeechCommandException):
    """発言者に現在地が設定されていない（発言・シャウトには位置が必要）"""

    def __init__(self, player_id: int):
        super().__init__(
            f"発言には現在地の設定が必要です: player_id={player_id}",
            player_id=player_id,
        )
