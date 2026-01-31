from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.item.exception import ItemInstanceIdValidationException


@dataclass(frozen=True)
class ItemInstanceId:
    """アイテムインスタンスID値オブジェクト

    IDは負の値ではいけません。
    """
    value: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.value <= 0:
            raise ItemInstanceIdValidationException(self.value)

    @classmethod
    def create(cls, value: Union[int, str]) -> "ItemInstanceId":
        """intまたはstrからItemInstanceIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise ItemInstanceIdValidationException(value)
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
        if not isinstance(other, ItemInstanceId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self.value)
