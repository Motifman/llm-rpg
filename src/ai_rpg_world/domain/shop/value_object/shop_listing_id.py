from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.shop.exception.shop_exception import ShopListingIdValidationException


@dataclass(frozen=True)
class ShopListingId:
    """ショップリストID値オブジェクト

    ショップ内で一意のリストID。正の整数である必要があります。
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ShopListingIdValidationException(
                f"Shop listing ID must be positive: {self.value}"
            )

    @classmethod
    def create(cls, value: Union[int, str]) -> "ShopListingId":
        """intまたはstrからShopListingIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise ShopListingIdValidationException(f"Invalid listing ID format: {value}")
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShopListingId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
