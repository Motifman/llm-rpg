from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.sns.exception import UserIdValidationException


@dataclass(frozen=True)
class UserId:
    """ユーザーID値オブジェクト

    IDは負の値ではいけません。
    """
    value: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.value <= 0:
            raise UserIdValidationException(self.value)

    @classmethod
    def create(cls, value: Union[int, str]) -> "UserId":
        """intまたはstrからUserIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise UserIdValidationException(value)
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        """文字列としてのID"""
        return str(self.value)

    def __int__(self) -> int:
        """intとしてのID"""
        return self.value

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, UserId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self.value)
