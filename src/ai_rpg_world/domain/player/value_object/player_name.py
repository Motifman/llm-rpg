from dataclasses import dataclass

from ai_rpg_world.domain.player.exception.player_exceptions import PlayerNameValidationException


_MIN_NAME_LENGTH = 2
_MAX_NAME_LENGTH = 16


@dataclass(frozen=True)
class PlayerName:
    """プレイヤー名値オブジェクト。

    日本語の 2 文字名 (例: 「リン」「カイト」← カイトは 3 だが「リン」は 2)
    がシナリオ cast として一般的なため、最低長 2 文字とする。
    実 LLM 試走 (Issue #264) で forbidden_library_demo のキャラクター名
    「リン」(2 文字) が validation で弾かれ tick=1 即死した issue を受けて、
    最低長 3 → 2 に緩和 (Issue #264 第16回実験の所見)。
    """
    value: str

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if not self.value:
            raise PlayerNameValidationException("Name cannot be empty")

        length = len(self.value)
        if not (_MIN_NAME_LENGTH <= length <= _MAX_NAME_LENGTH):
            raise PlayerNameValidationException(
                f"Name must be between {_MIN_NAME_LENGTH} and {_MAX_NAME_LENGTH} characters. "
                f"current: {length}"
            )
