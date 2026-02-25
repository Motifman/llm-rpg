from dataclasses import dataclass
from ai_rpg_world.domain.shop.exception.shop_exception import ShopListingPriceValidationException


@dataclass(frozen=True)
class ShopListingPrice:
    """ショップ販売価格（1単位あたりゴールド）の値オブジェクト

    1以上の値を持ちます。
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ShopListingPriceValidationException(
                f"Shop listing price must be 1 or more. value: {self.value}"
            )

    @classmethod
    def of(cls, value: int) -> "ShopListingPrice":
        """ShopListingPriceを作成するファクトリメソッド"""
        return cls(value)

    def __str__(self) -> str:
        return f"{self.value} G"

    def __repr__(self) -> str:
        return f"ShopListingPrice({self.value})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShopListingPrice):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __int__(self) -> int:
        return self.value
