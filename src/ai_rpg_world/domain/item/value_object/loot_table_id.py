from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.item.exception.item_exception import LootTableIdValidationException


@dataclass(frozen=True)
class LootTableId:
    """ドロップテーブルID値オブジェクト"""
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise LootTableIdValidationException(
                f"LootTableId must be positive: {self.value}"
            )

    @classmethod
    def create(cls, value: Union[int, str]) -> "LootTableId":
        """int または str（数値文字列）から LootTableId を作成する。"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise LootTableIdValidationException(
                    f"Invalid LootTableId format: {value}"
                )
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LootTableId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
