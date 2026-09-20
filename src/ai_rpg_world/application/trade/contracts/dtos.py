from dataclasses import dataclass
from datetime import datetime

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity


@dataclass(frozen=True)
class TradeDto:
    """取引DTO"""
    trade_id: int
    seller_id: int
    seller_name: str
    buyer_id: int | None
    buyer_name: str | None
    requested_gold: int
    status: str
    created_at: datetime

    # アイテム情報
    item_instance_id: int
    item_name: str
    item_quantity: int
    item_type: str
    item_rarity: str
    item_description: str
    item_equipment_type: str | None

    # 耐久度情報
    durability_current: int | None
    durability_max: int | None


@dataclass(frozen=True)
class TradeListDto:
    """取引一覧DTO（カーソルベースページング対応）"""
    trades: list[TradeDto]
    next_cursor: str | None = None


@dataclass(frozen=True)
class TradeSearchFilterDto:
    """取引検索フィルタDTO（アプリケーション層）"""
    item_name: str | None = None
    item_types: list[str] | None = None
    rarities: list[str] | None = None
    equipment_types: list[str] | None = None
    min_price: int | None = None
    max_price: int | None = None
    statuses: list[str] | None = None


@dataclass(frozen=True)
class TradeCommandResultDto:
    """取引コマンド実行結果DTO"""
    success: bool
    message: str
    data: dict | None = None
