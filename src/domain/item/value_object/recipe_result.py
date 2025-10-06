from dataclasses import dataclass
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.exception.item_exception import QuantityValidationException


@dataclass(frozen=True)
class RecipeResult:
    """レシピ結果値オブジェクト

    レシピで作成されるアイテムの情報（アイテム種別と数量）を保持する。
    """
    item_spec_id: ItemSpecId
    quantity: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.quantity <= 0:
            raise QuantityValidationException(f"Recipe result: quantity must be positive, got {self.quantity}")

    def __str__(self) -> str:
        """文字列表現"""
        return f"{self.item_spec_id} x{self.quantity}"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, RecipeResult):
            return NotImplemented
        return (self.item_spec_id == other.item_spec_id and
                self.quantity == other.quantity)

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash((self.item_spec_id, self.quantity))
