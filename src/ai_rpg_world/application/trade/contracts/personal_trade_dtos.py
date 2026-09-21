from dataclasses import dataclass


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
    item_equipment_type: str | None
    durability_current: int | None
    durability_max: int | None
    requested_gold: int
    seller_name: str
    created_at: str


@dataclass(frozen=True)
class PersonalTradeListDto:
    """個別取引出品一覧DTO"""
    listings: list[PersonalTradeListingDto]
    next_cursor: str | None
