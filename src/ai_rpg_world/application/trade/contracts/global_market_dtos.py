from dataclasses import dataclass
from typing import List, Optional

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity


@dataclass(frozen=True)
class GlobalMarketFilterDto:
    """グローバル取引所フィルタDTO（ステータスフィルタなし）"""
    item_name: Optional[str] = None
    item_types: Optional[List[str]] = None
    rarities: Optional[List[str]] = None
    equipment_types: Optional[List[str]] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None


@dataclass(frozen=True)
class GlobalMarketListingDto:
    """グローバル取引所出品DTO"""
    trade_id: int
    item_spec_id: int
    item_instance_id: int
    item_name: str
    item_quantity: int
    item_type: str
    item_rarity: str
    item_equipment_type: Optional[str]
    status: str
    created_at: str
    durability_current: Optional[int]
    durability_max: Optional[int]
    requested_gold: int


@dataclass(frozen=True)
class GlobalMarketListDto:
    """グローバル取引所出品一覧DTO"""
    listings: List[GlobalMarketListingDto]
    next_cursor: Optional[str]
