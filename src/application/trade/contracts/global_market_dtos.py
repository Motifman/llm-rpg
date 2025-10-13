from dataclasses import dataclass
from typing import List, Optional

from src.domain.item.enum.item_enum import ItemType, Rarity


@dataclass(frozen=True)
class GlobalMarketFilterDto:
    """グローバル取引所フィルタDTO"""
    item_type: Optional[ItemType] = None
    item_rarity: Optional[Rarity] = None
    search_text: Optional[str] = None
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
    durability_current: Optional[int]
    durability_max: Optional[int]
    requested_gold: int


@dataclass(frozen=True)
class GlobalMarketListDto:
    """グローバル取引所出品一覧DTO"""
    listings: List[GlobalMarketListingDto]
    total_count: int
    has_next_page: bool
