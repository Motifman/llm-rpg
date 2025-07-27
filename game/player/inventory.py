from typing import List, Dict, Optional
from game.item.item import Item, StackableItem, UniqueItem
from game.item.equipment_item import Weapon, Armor
from game.item.consumable_item import ConsumableItem


class Inventory:
    def __init__(self):
        # スタック可能アイテム用
        self.item_counts: Dict[str, int] = {}
        self.item_references: Dict[str, StackableItem] = {}
        # 固有アイテム用
        self.unique_items: Dict[str, UniqueItem] = {}

    def add_item(self, item: Item):
        # 固有アイテムの場合は特別処理
        if isinstance(item, UniqueItem):
            self._add_unique_item(item)
        elif isinstance(item, StackableItem):
            self._add_stackable_item(item)
        else:
            # 通常のアイテム（後方互換性のため）
            if item.item_id in self.item_counts:
                self.item_counts[item.item_id] += 1
            else:
                self.item_counts[item.item_id] = 1
                self.item_references[item.item_id] = item
    
    def _add_stackable_item(self, item: StackableItem):
        """スタック可能アイテムを追加"""
        if item.item_id in self.item_counts:
            self.item_counts[item.item_id] += 1
        else:
            self.item_counts[item.item_id] = 1
            self.item_references[item.item_id] = item
    
    def _add_unique_item(self, item: UniqueItem):
        """固有アイテムを追加"""
        # 固有アイテムは個別に管理
        self.unique_items[item.get_unique_id()] = item

    def remove_item(self, item: Item):
        if isinstance(item, UniqueItem):
            self.remove_item_by_id(item.item_id, 1, item.get_unique_id())
        else:
            self.remove_item_by_id(item.item_id, 1)
    
    def remove_item_by_id(self, item_id: str, count: int = 1, unique_id: Optional[str] = None) -> int:
        # 固有アイテムの場合は特別処理
        if unique_id and unique_id in self.unique_items:
            item = self.unique_items[unique_id]
            if item.item_id == item_id:
                del self.unique_items[unique_id]
                return 1
            else:
                return 0
        
        # 固有アイテムの場合は特別処理（unique_id指定なし）
        for unique_id_key, item in list(self.unique_items.items()):
            if item.item_id == item_id:
                if count > 0:
                    del self.unique_items[unique_id_key]
                    return 1
                else:
                    return 0
        
        # スタック可能アイテム
        if item_id not in self.item_counts:
            return 0
        
        if count <= 0:
            return 0
        
        current_count = self.item_counts[item_id]
        removed_count = min(count, current_count)
        
        if removed_count == current_count:
            del self.item_counts[item_id]
            del self.item_references[item_id]
        else:
            self.item_counts[item_id] -= removed_count
        
        return removed_count
    
    def get_item_by_id(self, item_id: str, unique_id: Optional[str] = None) -> Optional[Item]:
        # 固有アイテムを先にチェック
        if unique_id and unique_id in self.unique_items:
            item = self.unique_items[unique_id]
            if item.item_id == item_id:
                return item
            else:
                return None
        
        # 固有アイテムを先にチェック（unique_id指定なし）
        for item in self.unique_items.values():
            if item.item_id == item_id:
                return item
        
        # スタック可能アイテム
        return self.item_references.get(item_id)
    
    def get_item_count(self, item_id: str) -> int:
        # 固有アイテムの場合は該当するアイテム数をカウント
        unique_count = 0
        for item in self.unique_items.values():
            if item.item_id == item_id:
                unique_count += 1
        
        if unique_count > 0:
            return unique_count
        
        # スタック可能アイテム
        return self.item_counts.get(item_id, 0)
    
    def has_item(self, item_id: str, unique_id: Optional[str] = None) -> bool:
        # 固有アイテムを先にチェック
        if unique_id:
            return unique_id in self.unique_items and self.unique_items[unique_id].item_id == item_id
        
        for item in self.unique_items.values():
            if item.item_id == item_id:
                return True
        
        # スタック可能アイテム
        return item_id in self.item_counts and self.item_counts[item_id] > 0
    
    def get_items(self) -> List[Item]:
        items = []
        
        # 固有アイテムを追加
        items.extend(self.unique_items.values())
        
        # スタック可能アイテムを追加
        for item_id, count in self.item_counts.items():
            item = self.item_references[item_id]
            for _ in range(count):
                items.append(item)
        
        return items
    
    def get_summary(self) -> str:
        items = []
        for item_id, count in self.item_counts.items():
            item = self.item_references[item_id]
            items.append(f"{item} (x{count})")
        
        # 固有アイテムも追加
        for unique_item in self.unique_items.values():
            items.append(f"{unique_item} (固有)")
        
        return "\n".join(items)
    
    def get_inventory_display(self) -> str:
        if not self.item_counts and not self.unique_items:
            return "インベントリは空です。"
        
        display_lines = ["=== インベントリ ==="]
        
        # スタック可能アイテム
        for item_id, count in sorted(self.item_counts.items()):
            item = self.item_references[item_id]
            display_lines.append(f"• {item.item_id} x{count}")
            display_lines.append(f"  {item.description}")
            display_lines.append("")
        
        # 固有アイテム
        for unique_item in self.unique_items.values():
            display_lines.append(f"• {unique_item.name} - {unique_item.get_status_description()}")
            display_lines.append(f"  {unique_item.description}")
            display_lines.append("")
        
        return "\n".join(display_lines)
    
    def get_total_item_count(self) -> int:
        return sum(self.item_counts.values()) + len(self.unique_items)
    
    def get_unique_item_count(self) -> int:
        return len(self.item_counts) + len(self.unique_items)

    def get_all_equipment_item_ids(self) -> List[str]:
        item_ids = []
        for item_id in self.item_counts.keys():
            item = self.item_references[item_id]
            if isinstance(item, Weapon) or isinstance(item, Armor):
                item_ids.append(item_id)
        
        # 固有アイテムからも装備可能なものを追加
        for unique_item in self.unique_items.values():
            if isinstance(unique_item, Weapon) or isinstance(unique_item, Armor):
                item_ids.append(unique_item.item_id)
        
        return item_ids

    def get_all_consumable_item_ids(self) -> List[str]:
        item_ids = []
        for item_id in self.item_counts.keys():
            item = self.item_references[item_id]
            if isinstance(item, ConsumableItem):
                item_ids.append(item_id)
        
        # 固有アイテムからも消費可能なものを追加
        for unique_item in self.unique_items.values():
            if isinstance(unique_item, ConsumableItem):
                item_ids.append(unique_item.item_id)
        
        return item_ids