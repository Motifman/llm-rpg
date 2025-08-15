from __future__ import annotations

from typing import Dict, List, Optional
from domain.item.item import Item
from domain.item.unique_item import UniqueItem


class Inventory:
    """RPG文脈のインベントリ・ドメインモデル

    将来のDBスキーマを念頭に、スタック可能アイテムとユニークアイテムを分離して管理する。
    - スタック可能: player_inventory_stackable (player_id, item_id, count)
    - ユニーク: player_inventory_unique (player_id, unique_item_id)
    """

    def __init__(self) -> None:
        # スタック可能アイテム: item_id -> count
        self._stackable_counts: Dict[int, int] = {}
        # 参照用にカタログItemを保持: item_id -> Item
        self._stackable_refs: Dict[int, Item] = {}
        # ユニークアイテム: unique_item_id -> UniqueItem
        self._unique_items: Dict[int, UniqueItem] = {}

    # ===== スタック可能アイテム =====
    def add_stackable(self, item: Item, count: int = 1) -> None:
        """スタック可能アイテムを追加"""
        assert count > 0, "count must be greater than 0"
        current = self._stackable_counts.get(item.item_id, 0)
        self._stackable_counts[item.item_id] = current + count
        if item.item_id not in self._stackable_refs:
            self._stackable_refs[item.item_id] = item

    def remove_stackable(self, item_id: int, count: int = 1) -> int:
        """スタック可能アイテムを削除"""
        if count <= 0:
            return 0
        if item_id not in self._stackable_counts:
            return 0
        current_count = self._stackable_counts[item_id]
        removed = min(count, current_count)
        remaining = current_count - removed
        if remaining <= 0:
            del self._stackable_counts[item_id]
            # 参照も削除
            self._stackable_refs.pop(item_id, None)
        else:
            self._stackable_counts[item_id] = remaining
        return removed

    def get_stackable_count(self, item_id: int) -> int:
        """スタック可能アイテムの数を取得"""
        return self._stackable_counts.get(item_id, 0)

    def has_stackable(self, item_id: int, at_least: int = 1) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        assert at_least > 0, "at_least must be greater than 0"
        return self.get_stackable_count(item_id) >= at_least

    def get_stackable(self, item_id: int) -> Optional[Item]:
        """スタック可能アイテムを取得"""
        return self._stackable_refs.get(item_id)

    # ===== ユニークアイテム =====
    def add_unique(self, unique_item: UniqueItem) -> None:
        """ユニークアイテムを追加"""
        # 同じunique_idが既に存在していないことを前提
        self._unique_items[unique_item.id] = unique_item

    def remove_unique(self, unique_item_id: int) -> bool:
        """ユニークアイテムを削除"""
        if unique_item_id in self._unique_items:
            del self._unique_items[unique_item_id]
            return True
        return False

    def get_unique(self, unique_item_id: int) -> Optional[UniqueItem]:
        """ユニークアイテムを取得"""
        return self._unique_items.get(unique_item_id)

    def list_uniques_by_item_id(self, item_id: int) -> List[UniqueItem]:
        """アイテムIDに紐づくユニークアイテムを取得"""
        return [u for u in self._unique_items.values() if u.item.item_id == item_id]

    def has_unique(self, unique_item_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        return unique_item_id in self._unique_items

    def has_unique_by_item_id(self, item_id: int) -> bool:
        """アイテムIDに紐づくユニークアイテムを持っているかどうか"""
        return any(u.item.item_id == item_id for u in self._unique_items.values())

    # ===== 集計/ユーティリティ =====
    def get_total_item_count(self) -> int:
        """アイテムの総数を取得"""
        return sum(self._stackable_counts.values()) + len(self._unique_items)

    def is_empty(self) -> bool:
        """インベントリが空かどうか"""
        return not self._stackable_counts and not self._unique_items

    def get_inventory_display(self) -> str:
        """インベントリの表示"""
        if self.is_empty():
            return "インベントリは空です。"
        lines: List[str] = ["=== インベントリ ==="]
        for item_id, count in sorted(self._stackable_counts.items()):
            item = self._stackable_refs[item_id]
            lines.append(f"• {item.name} x{count}")
            lines.append(f"  {item.description}")
            lines.append("")
        for unique in self._unique_items.values():
            tradable = "取引可" if unique.can_be_traded() else "取引不可"
            lines.append(f"• {unique.item.name} (unique:{unique.id}) [{tradable}]")
            lines.append(f"  耐久度:{unique.durability} 攻:{unique.attack or 0} 防:{unique.defense or 0} 速:{unique.speed or 0}")
            lines.append("")
        return "\n".join(lines)


