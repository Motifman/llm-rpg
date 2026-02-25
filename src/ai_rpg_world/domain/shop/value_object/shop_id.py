from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.shop.exception.shop_exception import ShopIdValidationException


@dataclass(frozen=True)
class ShopId:
    """ショップID値オブジェクト

    IDは正の整数である必要があります。
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ShopIdValidationException(f"Shop ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "ShopId":
        """intまたはstrからShopIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise ShopIdValidationException(f"Invalid Shop ID format: {value}")
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShopId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
