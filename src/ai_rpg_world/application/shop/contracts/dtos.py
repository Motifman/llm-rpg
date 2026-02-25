"""ショップコマンド・クエリ結果DTO"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class ShopCommandResultDto:
    """ショップコマンド実行結果DTO"""
    success: bool
    message: str
    data: Optional[dict] = None


# --- クエリ用DTO ---


@dataclass(frozen=True)
class ShopSummaryDto:
    """ショップサマリDTO（一覧・ロケーション別）"""
    shop_id: int
    spot_id: int
    location_area_id: int
    name: str
    description: str
    owner_ids: List[int]
    listing_count: int
    created_at: datetime


@dataclass(frozen=True)
class ShopListingDto:
    """ショップ出品リストDTO"""
    shop_id: int
    listing_id: int
    item_instance_id: int
    item_name: str
    item_spec_id: int
    price_per_unit: int
    quantity: int
    listed_by: int
    listed_at: Optional[datetime] = None


@dataclass(frozen=True)
class ShopDetailDto:
    """ショップ詳細DTO（サマリ＋出品一覧）"""
    summary: ShopSummaryDto
    listings: List[ShopListingDto]
