from __future__ import annotations

from typing import List, Optional, ClassVar, cast, Union, Dict
from dataclasses import dataclass
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.unique_item import UniqueItem
from src.domain.player.value_object.base_status import BaseStatus


@dataclass
class InventorySlot:
    """インベントリのスロット"""
    slot_id: int
    content: Optional[Union[ItemQuantity, UniqueItem]] = None
    MAX_STACK_SIZE: ClassVar[int] = 99

    @classmethod
    def create_empty(cls, slot_id: int) -> InventorySlot:
        return cls(slot_id, None)
    
    def __post_init__(self):
        if self.slot_id < 0:
            raise ValueError(f"Slot ID must be >= 0: {self.slot_id}")

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
    
    def add_stackable(self, item: ItemQuantity) -> None:
        """スタック可能アイテムを追加"""
        if self.can_stack_with(item):
            if self.is_empty():
                self.content = item
            else:
                self.content = self.content.merge(item)
        else:
            raise ValueError(f"Cannot stack {self.content} with {item}. max_quantity: {self.MAX_STACK_SIZE}")
    
    def add_unique(self, item: UniqueItem) -> None:
        """ユニークアイテムを追加"""
        if self.is_empty():
            self.content = item
        else:
            raise ValueError(f"Slot already contains a unique item: {self.content}")
    
    def has_unique(self, unique_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        if self.is_empty():
            return False
        if not self.is_unique():
            return False
        if self.content.unique_id != unique_id:
            return False
        return True
    
    def remove_unique(self, unique_id: int) -> Optional[UniqueItem]:
        """ユニークアイテムを削除"""
        if self.has_unique(unique_id):
            unique_item_to_remove = cast(UniqueItem, self.content)
            self.content = None
            return unique_item_to_remove
        return None
    
    def has_stackable(self, item_type_id: int, quantity: int) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        if self.is_empty():
            return False
        if not self.is_stackable():
            return False
        if self.content.item.item_id != item_type_id:
            return False
        if self.content.quantity < quantity:
            return False
        return True
    
    def remove_stackable(self, item_type_id: int, quantity: int) -> Optional[ItemQuantity]:
        """スタック可能アイテムを削除"""
        if self.has_stackable(item_type_id, quantity):
            if self.content.quantity == quantity:
                # 全量削除の場合
                pop_item = self.content
                self.content = None
                return pop_item
            else:
                # 一部削除の場合
                pop_item, remaining_item = self.content.split(quantity)
                self.content = remaining_item
                return pop_item
        return None


class Inventory:
    """インベントリ"""
    def __init__(self, slots: List[InventorySlot], max_slots: int):
        self.slots = slots
        self.max_slots = max_slots

        self._slot_index: Dict[int, InventorySlot] = {}  # slot_id -> InventorySlot
        self._item_id_index: Dict[int, List[InventorySlot]] = {}  # item_id -> List[InventorySlot]
        self._unique_id_index: Dict[int, InventorySlot] = {}  # unique_id -> InventorySlot
        
        self._rebuild_indexes()
    
    @classmethod
    def create_empty(cls, max_slots: int) -> Inventory:
        return cls([InventorySlot.create_empty(i) for i in range(max_slots)], max_slots)

    def _rebuild_indexes(self) -> None:
        """インデックスを再構築"""
        self._slot_index.clear()
        self._item_id_index.clear()
        self._unique_id_index.clear()
        
        for slot in self.slots:
            # slot_idインデックス
            self._slot_index[slot.slot_id] = slot
            
            if not slot.is_empty():
                if slot.is_stackable():
                    # item_idインデックス
                    item_quantity = cast(ItemQuantity, slot.content)
                    item_id = item_quantity.item.item_id
                    if item_id not in self._item_id_index:
                        self._item_id_index[item_id] = []
                    self._item_id_index[item_id].append(slot)
                elif slot.is_unique():
                    # unique_idインデックス
                    unique_item = cast(UniqueItem, slot.content)
                    self._unique_id_index[unique_item.unique_id] = slot
    
    def _update_indexes_after_add(self, slot: InventorySlot) -> None:
        """アイテム追加後のインデックス更新"""
        if slot.is_stackable():
            item_quantity = cast(ItemQuantity, slot.content)
            item_id = item_quantity.item.item_id
            if item_id not in self._item_id_index:
                self._item_id_index[item_id] = []
            if slot not in self._item_id_index[item_id]:
                self._item_id_index[item_id].append(slot)
        elif slot.is_unique():
            unique_item = cast(UniqueItem, slot.content)
            self._unique_id_index[unique_item.unique_id] = slot
    
    def _update_indexes_after_remove(self, slot: InventorySlot, removed_item: Union[ItemQuantity, UniqueItem]) -> None:
        """アイテム削除後のインデックス更新"""
        if isinstance(removed_item, ItemQuantity):
            item_id = removed_item.item.item_id
            if slot.is_empty() and item_id in self._item_id_index:
                self._item_id_index[item_id].remove(slot)
                if not self._item_id_index[item_id]:
                    del self._item_id_index[item_id]
        elif isinstance(removed_item, UniqueItem):
            unique_id = removed_item.unique_id
            if unique_id in self._unique_id_index:
                del self._unique_id_index[unique_id]
    
    # ===== 効率的な検索メソッド =====
    
    def get_slot_by_id(self, slot_id: int) -> Optional[InventorySlot]:
        """slot_idでスロットを取得 (O(1))"""
        return self._slot_index.get(slot_id)
    
    def get_item_by_slot_id(self, slot_id: int) -> Optional[Union[ItemQuantity, UniqueItem]]:
        """slot_idでアイテムの実態を取得 (O(1))"""
        slot = self.get_slot_by_id(slot_id)
        return slot.content if slot else None
    
    def get_slots_by_item_id(self, item_id: int) -> List[InventorySlot]:
        """item_idで該当するスロット一覧を取得 (O(1))"""
        return self._item_id_index.get(item_id, []).copy()
    
    def get_item_by_unique_id(self, unique_id: int) -> Optional[UniqueItem]:
        """unique_idでユニークアイテムを取得 (O(1))"""
        slot = self._unique_id_index.get(unique_id)
        return cast(UniqueItem, slot.content) if slot else None
    
    def get_slot_by_unique_id(self, unique_id: int) -> Optional[InventorySlot]:
        """unique_idでスロットを取得 (O(1))"""
        return self._unique_id_index.get(unique_id)
    
    def find_stackable_items_by_id(self, item_id: int) -> List[ItemQuantity]:
        """item_idで該当するスタック可能アイテム一覧を取得"""
        slots = self.get_slots_by_item_id(item_id)
        return [cast(ItemQuantity, slot.content) for slot in slots if slot.is_stackable()]
    
    def get_total_quantity_by_item_id(self, item_id: int) -> int:
        """item_idの総数量を取得"""
        return sum(item.quantity for item in self.find_stackable_items_by_id(item_id))
    
    def add_item(self, item_to_add: ItemQuantity | UniqueItem) -> bool:
        """アイテムを追加"""
        if isinstance(item_to_add, ItemQuantity):
            stackable_slot = self._find_stackable_slot(item_to_add)
            if stackable_slot:
                stackable_slot.add_stackable(item_to_add)
                self._update_indexes_after_add(stackable_slot)
                return True
            else:
                return False
        elif isinstance(item_to_add, UniqueItem):
            empty_slot = self._find_empty_slot()
            if empty_slot:
                empty_slot.add_unique(item_to_add)
                self._update_indexes_after_add(empty_slot)
                return True
            else:
                return False
        else:
            raise ValueError(f"Item is not stackable: {item_to_add}")

    def remove_item(self, item_id: int = None, quantity: int = 1, unique_id: Optional[int] = None, slot_id: Optional[int] = None) -> Optional[ItemQuantity | UniqueItem]:
        """アイテムを削除（複数の検索方法をサポート）"""
        slot = None
        
        if slot_id is not None:
            # slot_idで直接指定
            slot = self.get_slot_by_id(slot_id)
        elif unique_id is not None:
            # unique_idで検索
            slot = self.get_slot_by_unique_id(unique_id)
        elif item_id is not None:
            # item_idで検索
            slot = self._find_slot_by_item_type_id_and_quantity(item_id, quantity)
        
        if not slot:
            return None
        
        removed_item = None
        if unique_id is not None and slot.is_unique():
            removed_item = slot.remove_unique(unique_id)
        elif item_id is not None and slot.is_stackable():
            removed_item = slot.remove_stackable(item_id, quantity)
        
        if removed_item:
            self._update_indexes_after_remove(slot, removed_item)
        
        return removed_item
    
    def has_stackable(self, item_id: int, quantity: int) -> bool:
        """スタック可能アイテムを持っているかどうか（高速化）"""
        return self.get_total_quantity_by_item_id(item_id) >= quantity
    
    def has_unique(self, unique_id: int) -> bool:
        """ユニークアイテムを持っているかどうか（高速化）"""
        return unique_id in self._unique_id_index
    
    def search_item(self, item_id: int = None, unique_id: Optional[int] = None, slot_id: Optional[int] = None) -> Optional[ItemQuantity | UniqueItem]:
        """汎用アイテム検索"""
        if slot_id is not None:
            return self.get_item_by_slot_id(slot_id)
        elif unique_id is not None:
            return self.get_item_by_unique_id(unique_id)
        elif item_id is not None:
            items = self.find_stackable_items_by_id(item_id)
            return items[0] if items else None
        return None

    def _find_empty_slot(self) -> Optional[InventorySlot]:
        """空のスロットを探す"""
        return next((s for s in self.slots if s.is_empty()), None)
    
    def _find_stackable_slot(self, item_to_add: ItemQuantity) -> Optional[InventorySlot]:
        """スタック可能アイテムを追加するスロットを探す"""
        return next((s for s in self.slots if s.can_stack_with(item_to_add)), None)
    
    def _find_slot_by_unique_id(self, unique_id: int) -> Optional[InventorySlot]:
        """ユニークアイテムに紐づくスロットを探す"""
        return next((s for s in self.slots if s.has_unique(unique_id)), None)
    
    def _find_slot_by_item_type_id_and_quantity(self, item_type_id: int, quantity: int) -> Optional[InventorySlot]:
        """アイテムIDに紐づくスロットを探す"""
        return next((s for s in self.slots if s.has_stackable(item_type_id, quantity)), None)
        


# class Inventory:
#     """RPG文脈のインベントリ・ドメインモデル

#     将来のDBスキーマを念頭に、スタック可能アイテムとユニークアイテムを分離して管理する。
#     - スタック可能: player_inventory_stackable (player_id, item_id, count)
#     - ユニーク: player_inventory_unique (player_id, unique_item_id)
#     """

#     def __init__(self) -> None:
#         # スタック可能アイテム: item_id -> count
#         self._stackable_counts: Dict[int, int] = {}
#         # 参照用にカタログItemを保持: item_id -> Item
#         self._stackable_refs: Dict[int, Item] = {}
#         # ユニークアイテム: unique_item_id -> UniqueItem
#         self._unique_items: Dict[int, UniqueItem] = {}

#     # ===== スタック可能アイテム =====
#     def add_stackable(self, item: Item, count: int = 1) -> None:
#         """スタック可能アイテムを追加"""
#         assert count > 0, "count must be greater than 0"
#         current = self._stackable_counts.get(item.item_id, 0)
#         self._stackable_counts[item.item_id] = current + count
#         if item.item_id not in self._stackable_refs:
#             self._stackable_refs[item.item_id] = item

#     def remove_stackable(self, item_id: int, count: int = 1) -> int:
#         """スタック可能アイテムを削除"""
#         if count <= 0:
#             return 0
#         if item_id not in self._stackable_counts:
#             return 0
#         current_count = self._stackable_counts[item_id]
#         removed = min(count, current_count)
#         remaining = current_count - removed
#         if remaining <= 0:
#             del self._stackable_counts[item_id]
#             # 参照も削除
#             self._stackable_refs.pop(item_id, None)
#         else:
#             self._stackable_counts[item_id] = remaining
#         return removed

#     def get_stackable_count(self, item_id: int) -> int:
#         """スタック可能アイテムの数を取得"""
#         return self._stackable_counts.get(item_id, 0)

#     def has_stackable(self, item_id: int, at_least: int = 1) -> bool:
#         """スタック可能アイテムを持っているかどうか"""
#         assert at_least > 0, "at_least must be greater than 0"
#         return self.get_stackable_count(item_id) >= at_least

#     def get_stackable(self, item_id: int) -> Optional[Item]:
#         """スタック可能アイテムを取得"""
#         return self._stackable_refs.get(item_id)

#     # ===== ユニークアイテム =====
#     def add_unique(self, unique_item: UniqueItem) -> None:
#         """ユニークアイテムを追加"""
#         # 同じunique_idが既に存在していないことを前提
#         self._unique_items[unique_item.id] = unique_item

#     def remove_unique(self, unique_item_id: int) -> bool:
#         """ユニークアイテムを削除"""
#         if unique_item_id in self._unique_items:
#             del self._unique_items[unique_item_id]
#             return True
#         return False

#     def get_unique(self, unique_item_id: int) -> Optional[UniqueItem]:
#         """ユニークアイテムを取得"""
#         return self._unique_items.get(unique_item_id)

#     def list_uniques_by_item_id(self, item_id: int) -> List[UniqueItem]:
#         """アイテムIDに紐づくユニークアイテムを取得"""
#         return [u for u in self._unique_items.values() if u.item.item_id == item_id]

#     def has_unique(self, unique_item_id: int) -> bool:
#         """ユニークアイテムを持っているかどうか"""
#         return unique_item_id in self._unique_items

#     def has_unique_by_item_id(self, item_id: int) -> bool:
#         """アイテムIDに紐づくユニークアイテムを持っているかどうか"""
#         return any(u.item.item_id == item_id for u in self._unique_items.values())

#     # ===== 集計/ユーティリティ =====
#     def get_total_item_count(self) -> int:
#         """アイテムの総数を取得"""
#         return sum(self._stackable_counts.values()) + len(self._unique_items)

#     def is_empty(self) -> bool:
#         """インベントリが空かどうか"""
#         return not self._stackable_counts and not self._unique_items

#     def get_inventory_display(self) -> str:
#         """インベントリの表示"""
#         if self.is_empty():
#             return "インベントリは空です。"
#         lines: List[str] = ["=== インベントリ ==="]
#         for item_id, count in sorted(self._stackable_counts.items()):
#             item = self._stackable_refs[item_id]
#             lines.append(f"• {item.name} x{count}")
#             lines.append(f"  {item.description}")
#             lines.append("")
#         for unique in self._unique_items.values():
#             tradable = "取引可" if unique.can_be_traded() else "取引不可"
#             lines.append(f"• {unique.item.name} (unique:{unique.id}) [{tradable}]")
#             lines.append(f"  耐久度:{unique.durability} 攻:{unique.attack or 0} 防:{unique.defense or 0} 速:{unique.speed or 0}")
#             lines.append("")
#         return "\n".join(lines)