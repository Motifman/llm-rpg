from dataclasses import dataclass
from typing import Optional
from src.domain.trade.enum.trade_enum import TradeStatus


@dataclass(frozen=True)
class OfferItemCommand:
    """アイテム出品コマンド"""
    seller_id: int
    item_instance_id: int
    slot_id: int
    requested_gold: int
    is_direct: bool = False
    target_player_id: Optional[int] = None


@dataclass(frozen=True)
class AcceptTradeCommand:
    """取引受諾コマンド"""
    trade_id: int
    buyer_id: int


@dataclass(frozen=True)
class CancelTradeCommand:
    """取引キャンセルコマンド"""
    trade_id: int
    player_id: int
