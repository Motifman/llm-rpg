from dataclasses import dataclass

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity


@dataclass(frozen=True)
class GlobalMarketFilterDto:
    """グローバル取引所フィルタDTO（ステータスフィルタなし）"""
    item_name: str | None = None
    item_types: list[str] | None = None
    rarities: list[str] | None = None
    equipment_types: list[str] | None = None
    min_price: int | None = None
    max_price: int | None = None


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
    item_equipment_type: str | None
    status: str
    created_at: str
    durability_current: int | None
    durability_max: int | None
    requested_gold: int


@dataclass(frozen=True)
class GlobalMarketListDto:
    """グローバル取引所出品一覧DTO"""
    listings: list[GlobalMarketListingDto]
    next_cursor: str | None
