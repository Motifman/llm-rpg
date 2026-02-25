"""ショップコマンド定義"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CreateShopCommand:
    """ショップ開設コマンド"""
    spot_id: int
    location_area_id: int
    owner_id: int
    name: str = ""
    description: str = ""


@dataclass(frozen=True)
class ListShopItemCommand:
    """ショップ出品コマンド"""
    shop_id: int
    player_id: int  # オーナー
    slot_id: int  # 出品するインベントリスロット
    price_per_unit: int


@dataclass(frozen=True)
class UnlistShopItemCommand:
    """ショップ取り下げコマンド"""
    shop_id: int
    listing_id: int
    player_id: int  # オーナー


@dataclass(frozen=True)
class PurchaseFromShopCommand:
    """ショップ購入コマンド"""
    shop_id: int
    listing_id: int
    buyer_id: int
    quantity: int
