from dataclasses import dataclass
from typing import List, Optional, Dict, cast, Union
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.unique_item import UniqueItem


@dataclass(frozen=True)
class InventorySlot:
    """インベントリのスロット（値オブジェクト）"""
    slot_id: int
    content: Optional[Union[ItemQuantity, UniqueItem]] = None
    MAX_STACK_SIZE: int = 99

    def __post_init__(self):
        if self.slot_id < 0:
            raise ValueError(f"Slot ID must be >= 0: {self.slot_id}")

    @classmethod
    def create_empty(cls, slot_id: int) -> "InventorySlot":
        return cls(slot_id=slot_id, content=None)

    def is_empty(self) -> bool:
        """スロットが空かどうか"""
        return self.content is None

    def is_stackable(self) -> bool:
        """スタック可能アイテムかどうか"""
        return isinstance(self.content, ItemQuantity)

    def is_unique(self) -> bool:
        """ユニークアイテムかどうか"""
        return isinstance(self.content, UniqueItem)

    def can_stack_with(self, item_to_add: ItemQuantity) -> bool:
        """スタック可能アイテムを追加したときに、スタックが可能かどうか"""
        if self.is_empty():
            return True
        if self.is_unique():
            return False

        existing = cast(ItemQuantity, self.content)
        if existing.item.item_id != item_to_add.item.item_id:
            return False
        return existing.quantity + item_to_add.quantity <= self.MAX_STACK_SIZE

    def with_stackable_added(self, item: ItemQuantity) -> "InventorySlot":
        """スタック可能アイテムを追加した新しいスロットを返す"""
        if not self.can_stack_with(item):
            raise ValueError(f"Cannot stack {self.content} with {item}. max_quantity: {self.MAX_STACK_SIZE}")

        if self.is_empty():
            return InventorySlot(slot_id=self.slot_id, content=item)
        else:
            merged = self.content.merge(item)
            return InventorySlot(slot_id=self.slot_id, content=merged)

    def with_unique_added(self, item: UniqueItem) -> "InventorySlot":
        """ユニークアイテムを追加した新しいスロットを返す"""
        if not self.is_empty():
            raise ValueError(f"Slot already contains a unique item: {self.content}")
        return InventorySlot(slot_id=self.slot_id, content=item)

    def with_item_removed(self) -> "InventorySlot":
        """アイテムを削除した新しいスロットを返す"""
        return InventorySlot(slot_id=self.slot_id, content=None)

    def has_unique(self, unique_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        if self.is_empty():
            return False
        if not self.is_unique():
            return False
        return self.content.unique_id == unique_id

    def has_stackable(self, item_type_id: int, quantity: int) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        if self.is_empty():
            return False
        if not self.is_stackable():
            return False
        if self.content.item.item_id != item_type_id:
            return False
        return self.content.quantity >= quantity

    def remove_unique(self, unique_id: int) -> Optional[UniqueItem]:
        """ユニークアイテムを削除した新しいスロットを返す"""
        if self.has_unique(unique_id):
            return cast(UniqueItem, self.content), InventorySlot(slot_id=self.slot_id, content=None)
        return None, self

    def remove_stackable(self, item_type_id: int, quantity: int) -> tuple[Optional[ItemQuantity], "InventorySlot"]:
        """スタック可能アイテムを削除した新しいスロットを返す"""
        if not self.has_stackable(item_type_id, quantity):
            return None, self

        if self.content.quantity == quantity:
            # 全量削除の場合
            return self.content, InventorySlot(slot_id=self.slot_id, content=None)
        else:
            # 一部削除の場合
            removed, remaining = self.content.split(quantity)
            return removed, InventorySlot(slot_id=self.slot_id, content=remaining)


@dataclass(frozen=True)
class InventorySlots:
    """インベントリスロットのコレクション（値オブジェクト）"""
    slots: List[InventorySlot]
    max_slots: int

    def __post_init__(self):
        if len(self.slots) > self.max_slots:
            raise ValueError(f"Number of slots ({len(self.slots)}) exceeds max_slots ({self.max_slots})")

    @classmethod
    def create_empty(cls, max_slots: int) -> "InventorySlots":
        slots = [InventorySlot.create_empty(i) for i in range(max_slots)]
        return cls(slots=slots, max_slots=max_slots)

    def get_slot_by_id(self, slot_id: int) -> Optional[InventorySlot]:
        """slot_idでスロットを取得"""
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        return None

    def get_slot_by_unique_id(self, unique_id: int) -> Optional[InventorySlot]:
        """unique_idでスロットを取得"""
        for slot in self.slots:
            if slot.has_unique(unique_id):
                return slot
        return None

    def find_slots_by_item_id(self, item_id: int) -> List[InventorySlot]:
        """item_idで該当するスロット一覧を取得"""
        return [slot for slot in self.slots if slot.is_stackable() and slot.content.item.item_id == item_id]

    def get_total_quantity_by_item_id(self, item_id: int) -> int:
        """item_idの総数量を取得"""
        return sum(slot.content.quantity for slot in self.find_slots_by_item_id(item_id))

    def find_empty_slot(self) -> Optional[InventorySlot]:
        """空のスロットを探す"""
        return next((slot for slot in self.slots if slot.is_empty()), None)

    def find_stackable_slot(self, item_to_add: ItemQuantity) -> Optional[InventorySlot]:
        """スタック可能アイテムを追加するスロットを探す"""
        return next((slot for slot in self.slots if slot.can_stack_with(item_to_add)), None)

    def has_stackable(self, item_id: int, quantity: int) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        return self.get_total_quantity_by_item_id(item_id) >= quantity

    def has_unique(self, unique_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        return self.get_slot_by_unique_id(unique_id) is not None

    def with_item_added(self, item: ItemQuantity | UniqueItem) -> "InventorySlots":
        """アイテムを追加した新しいInventorySlotsを返す"""
        if isinstance(item, ItemQuantity):
            # スタック可能なスロットを検索
            stackable_slot = self.find_stackable_slot(item)
            if stackable_slot:
                return self._with_slot_updated(stackable_slot.with_stackable_added(item))

            # 空のスロットを検索
            empty_slot = self.find_empty_slot()
            if empty_slot:
                return self._with_slot_updated(empty_slot.with_stackable_added(item))

            raise ValueError("No available slot for stackable item")

        elif isinstance(item, UniqueItem):
            # 空のスロットを検索
            empty_slot = self.find_empty_slot()
            if empty_slot:
                return self._with_slot_updated(empty_slot.with_unique_added(item))
            else:
                raise ValueError("No available slot for unique item")
        else:
            raise ValueError(f"Unsupported item type: {type(item)}")

    def with_item_removed(self, item_id: int = None, quantity: int = 1, unique_id: Optional[int] = None, slot_id: Optional[int] = None) -> tuple[Optional[ItemQuantity | UniqueItem], "InventorySlots"]:
        """アイテムを削除した新しいInventorySlotsを返す"""
        target_slot = None

        if slot_id is not None:
            target_slot = self.get_slot_by_id(slot_id)
        elif unique_id is not None:
            target_slot = self.get_slot_by_unique_id(unique_id)
        elif item_id is not None:
            # item_idで検索（最初の該当スロット）
            slots = self.find_slots_by_item_id(item_id)
            if slots:
                target_slot = slots[0]

        if not target_slot:
            return None, self

        if unique_id is not None and target_slot.is_unique():
            removed_item, new_slot = target_slot.remove_unique(unique_id)
        elif item_id is not None and target_slot.is_stackable():
            removed_item, new_slot = target_slot.remove_stackable(item_id, quantity)
        else:
            return None, self

        if removed_item:
            new_slots = self._with_slot_updated(new_slot)
            return removed_item, new_slots

        return None, self

    def _with_slot_updated(self, updated_slot: InventorySlot) -> "InventorySlots":
        """指定されたスロットを更新した新しいInventorySlotsを返す"""
        new_slots = []
        for slot in self.slots:
            if slot.slot_id == updated_slot.slot_id:
                new_slots.append(updated_slot)
            else:
                new_slots.append(slot)
        return InventorySlots(slots=new_slots, max_slots=self.max_slots)

    def is_full(self) -> bool:
        """インベントリが満杯かどうか"""
        return all(not slot.is_empty() for slot in self.slots)

    def get_free_slots_count(self) -> int:
        """空きスロット数を取得"""
        return sum(1 for slot in self.slots if slot.is_empty())
