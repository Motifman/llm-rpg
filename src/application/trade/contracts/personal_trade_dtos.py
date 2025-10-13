from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class PersonalTradeListingDto:
    """個別取引出品DTO"""
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
    seller_name: str


@dataclass(frozen=True)
class PersonalTradeListDto:
    """個別取引出品一覧DTO"""
    listings: List[PersonalTradeListingDto]
    total_count: int
    has_next_page: bool
