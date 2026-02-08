from dataclasses import dataclass
from typing import List, Optional
import random
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


from ai_rpg_world.domain.item.exception.item_exception import (
    LootTableValidationException,
    LootWeightValidationException,
    QuantityValidationException
)


@dataclass(frozen=True)
class LootEntry:
    """ドロップテーブルの各エントリー"""
    item_spec_id: ItemSpecId
    weight: int
    min_quantity: int = 1
    max_quantity: int = 1

    def __post_init__(self):
        if self.weight < 0:
            raise LootWeightValidationException(f"Weight cannot be negative: {self.weight}")
        if self.min_quantity <= 0:
            raise QuantityValidationException(f"Min quantity must be positive: {self.min_quantity}")
        if self.max_quantity < self.min_quantity:
            raise QuantityValidationException(
                f"Max quantity ({self.max_quantity}) cannot be less than min quantity ({self.min_quantity})"
            )


@dataclass(frozen=True)
class LootResult:
    """抽選結果"""
    item_spec_id: ItemSpecId
    quantity: int


class LootTableAggregate(AggregateRoot):
    """
    ドロップテーブルの集約。
    確率に基づいたアイテム抽選ロジックを持つ。
    """
    def __init__(
        self,
        loot_table_id: str,
        entries: List[LootEntry],
        name: str = ""
    ):
        super().__init__()
        self._validate_entries(entries)
        self._loot_table_id = loot_table_id
        self._entries = entries
        self._name = name
        self._total_weight = sum(entry.weight for entry in entries)

    @classmethod
    def create(
        cls,
        loot_table_id: str,
        entries: List[LootEntry],
        name: str = ""
    ) -> "LootTableAggregate":
        return cls(loot_table_id, entries, name)

    def _validate_entries(self, entries: List[LootEntry]):
        if not entries:
            raise LootTableValidationException("Loot table entries cannot be empty")
        
        total_weight = sum(entry.weight for entry in entries)
        if entries and total_weight <= 0:
            raise LootWeightValidationException("Total weight must be positive if entries exist")

    @property
    def loot_table_id(self) -> str:
        return self._loot_table_id

    @property
    def entries(self) -> List[LootEntry]:
        return list(self._entries)

    @property
    def name(self) -> str:
        return self._name

    def roll(self) -> Optional[LootResult]:
        """アイテムを抽選する。何も出ない場合はNoneを返す。"""
        if not self._entries or self._total_weight <= 0:
            return None

        r = random.randint(1, self._total_weight)
        current_weight = 0
        
        for entry in self._entries:
            current_weight += entry.weight
            if r <= current_weight:
                quantity = random.randint(entry.min_quantity, entry.max_quantity)
                return LootResult(entry.item_spec_id, quantity)
        
        return None
