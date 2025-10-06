from typing import List, Optional
from dataclasses import dataclass
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.durability import Durability
from src.domain.item.exception import QuantityValidationException


@dataclass(frozen=True)
class UpdateOperation:
    """更新操作"""
    item_instance_id: ItemInstanceId
    new_quantity: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.new_quantity <= 0:
            raise QuantityValidationException(f"Update operation: new_quantity must be positive, got {self.new_quantity}")


@dataclass(frozen=True)
class CreateOperation:
    """作成操作"""
    item_spec: ItemSpec
    quantity: int
    durability: Optional[Durability] = None

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.quantity <= 0:
            raise QuantityValidationException(f"Create operation: quantity must be positive, got {self.quantity}")


@dataclass(frozen=True)
class DeleteOperation:
    """削除操作"""
    item_instance_id: ItemInstanceId


@dataclass(frozen=True)
class MergePlan:
    """マージ計画

    アイテムマージのための操作計画を表す値オブジェクト。
    """
    update_operations: List[UpdateOperation]
    create_operations: List[CreateOperation]
    delete_operations: List[DeleteOperation]


@dataclass(frozen=True)
class ConsumedItem:
    """消費されたアイテム

    クラフトで消費されたアイテムの情報を保持する。
    """
    item_instance_id: ItemInstanceId
    consumed_quantity: int
    remaining_quantity: int

    def __post_init__(self):
        """バリデーション"""
        if self.consumed_quantity <= 0:
            raise QuantityValidationException(f"Consumed item: consumed_quantity must be positive, got {self.consumed_quantity}")
        if self.remaining_quantity < 0:
            raise QuantityValidationException(f"Consumed item: remaining_quantity must be non-negative, got {self.remaining_quantity}")


@dataclass(frozen=True)
class CraftingConsumptionPlan:
    """クラフト消費計画

    レシピの材料消費を実行するための計画。
    """
    consumed_items: List[ConsumedItem]
    update_operations: List[UpdateOperation]
    delete_operations: List[DeleteOperation]

    @property
    def total_consumed_quantity(self) -> int:
        """総消費数量"""
        return sum(item.consumed_quantity for item in self.consumed_items)
