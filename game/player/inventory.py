from typing import List, Dict
from game.item.item import Item
from game.item.equipment_item import Weapon, Armor
from game.item.consumable_item import ConsumableItem


class Inventory:
    def __init__(self):
        self.item_counts: Dict[str, int] = {}
        self.item_references: Dict[str, Item] = {}

    def add_item(self, item: Item):
        if item.item_id in self.item_counts:
            self.item_counts[item.item_id] += 1
        else:
            self.item_counts[item.item_id] = 1
            self.item_references[item.item_id] = item

    def remove_item(self, item: Item):
        self.remove_item_by_id(item.item_id, 1)
    
    def get_items(self) -> List[Item]:
        items = []
        for item_id, count in self.item_counts.items():
            item = self.item_references[item_id]
            for _ in range(count):
                items.append(item)
        return items
    
    def get_item_by_id(self, item_id: str) -> Item:
        return self.item_references.get(item_id)
    
    def get_item_count(self, item_id: str) -> int:
        return self.item_counts.get(item_id, 0)

    def remove_item_by_id(self, item_id: str, count: int = 1) -> int:
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
    
    def has_item(self, item_id: str) -> bool:
        return item_id in self.item_counts and self.item_counts[item_id] > 0
    
    def get_summary(self) -> str:
        items = []
        for item_id, count in self.item_counts.items():
            item = self.item_references[item_id]
            items.append(f"{item} (x{count})")
        return "\n".join(items)
    
    def get_inventory_display(self) -> str:
        if not self.item_counts:
            return "インベントリは空です。"
        
        display_lines = ["=== インベントリ ==="]
        
        for item_id, count in sorted(self.item_counts.items()):
            item = self.item_references[item_id]
            display_lines.append(f"• {item.item_id} x{count}")
            display_lines.append(f"  {item.description}")
            display_lines.append("")
        
        return "\n".join(display_lines)
    
    def get_total_item_count(self) -> int:
        return sum(self.item_counts.values())
    
    def get_unique_item_count(self) -> int:
        return len(self.item_counts)

    def get_all_equipment_item_ids(self) -> List[str]:
        item_ids = []
        for item_id in self.item_counts.keys():
            item = self.item_references[item_id]
            if isinstance(item, Weapon) or isinstance(item, Armor):
                item_ids.append(item_id)
        return item_ids

    def get_all_consumable_item_ids(self) -> List[str]:
        item_ids = []
        for item_id in self.item_counts.keys():
            item = self.item_references[item_id]
            if isinstance(item, ConsumableItem):
                item_ids.append(item_id)
        return item_ids