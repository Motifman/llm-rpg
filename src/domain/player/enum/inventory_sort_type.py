from enum import Enum


class InventorySortType(Enum):
    """インベントリソート基準"""
    ITEM_TYPE = "item_type"      # アイテムタイプ順
    RARITY = "rarity"           # レアリティ順
    NAME = "name"              # 名前順
