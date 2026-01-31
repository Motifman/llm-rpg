from dataclasses import dataclass

from ai_rpg_world.domain.player.exception.player_exceptions import PlayerNameValidationException


@dataclass(frozen=True)
class PlayerName:
    """プレイヤー名値オブジェクト"""
    value: str

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if not self.value:
            raise PlayerNameValidationException("Name cannot be empty")

        if not (3 <= len(self.value) <= 16):
            raise PlayerNameValidationException(f"Name must be between 3 and 16 characters. current: {len(self.value)}")
