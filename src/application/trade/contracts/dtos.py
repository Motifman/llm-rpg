from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


@dataclass(frozen=True)
class TradeDto:
    """取引DTO"""
    trade_id: int
    seller_id: int
    seller_name: str
    buyer_id: Optional[int]
    buyer_name: Optional[str]
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
    item_equipment_type: Optional[str]

    # 耐久度情報
    durability_current: Optional[int]
    durability_max: Optional[int]


@dataclass(frozen=True)
class TradeListDto:
    """取引一覧DTO（カーソルベースページング対応）"""
    trades: List[TradeDto]
    next_cursor: Optional[str] = None


@dataclass(frozen=True)
class TradeSearchFilterDto:
    """取引検索フィルタDTO（アプリケーション層）"""
    item_name: Optional[str] = None
    item_types: Optional[List[str]] = None
    rarities: Optional[List[str]] = None
    equipment_types: Optional[List[str]] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    statuses: Optional[List[str]] = None


@dataclass(frozen=True)
class TradeCommandResultDto:
    """取引コマンド実行結果DTO"""
    success: bool
    message: str
    data: Optional[dict] = None
