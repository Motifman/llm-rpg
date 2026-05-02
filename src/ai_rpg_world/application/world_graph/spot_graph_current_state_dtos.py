"""スポットグラフ用の現在状態スナップショット（LLM プロンプト向け）"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# --- 構造化エントリ（UiContextBuilder がラベル付与に使用） ---

@dataclass(frozen=True)
class SpotGraphInteractionEntry:
    action_name: str
    display_label: str


@dataclass(frozen=True)
class SpotGraphConnectionEntry:
    """接続先1件の構造化データ。"""
    destination_spot_id: int
    connection_name: str
    destination_spot_name: str
    is_passable: bool
    passage_condition_text: Optional[str] = None


@dataclass(frozen=True)
class SpotGraphObjectEntry:
    """スポット内オブジェクト1件の構造化データ。"""
    object_id: int
    name: str
    description: str
    interactions: Tuple[SpotGraphInteractionEntry, ...]


@dataclass(frozen=True)
class SpotGraphSubLocationEntry:
    """サブロケーション1件の構造化データ。"""
    sub_location_id: int
    name: str
    is_current: bool
    is_hidden: bool


@dataclass(frozen=True)
class SpotGraphWeatherEntry:
    """天候情報の構造化データ。屋外スポットのみ有効。"""
    weather_type: str
    weather_intensity: float
    is_outdoor: bool


@dataclass(frozen=True)
class SpotGraphAtmosphereEntry:
    """雰囲気情報の構造化データ。"""
    lighting: str
    sound_ambient: Optional[str]
    temperature: str
    smell: Optional[str]


@dataclass(frozen=True)
class SpotGraphInventoryItemEntry:
    """所持アイテム1件の構造化データ。"""
    item_spec_id: int
    name: str
    quantity: int


@dataclass(frozen=True)
class SpotGraphNearbyEntityEntry:
    """同スポットにいるエンティティ1件の構造化データ。"""
    entity_id: int
    display_name: str = ""


# --- スナップショット ---

@dataclass(frozen=True)
class SpotGraphPlayerSnapshotDto:
    """スポットグラフ上のプレイヤー周辺の読み取り専用スナップショット。"""

    current_spot_id: int
    current_spot_name: str
    current_spot_description: str
    travel_status_line: Optional[str]

    connections: Tuple[SpotGraphConnectionEntry, ...] = ()
    objects: Tuple[SpotGraphObjectEntry, ...] = ()
    sub_locations: Tuple[SpotGraphSubLocationEntry, ...] = ()
    atmosphere: Optional[SpotGraphAtmosphereEntry] = None
    weather: Optional[SpotGraphWeatherEntry] = None
    nearby_entities: Tuple[SpotGraphNearbyEntityEntry, ...] = ()
    inventory_items: Tuple[SpotGraphInventoryItemEntry, ...] = ()
    ground_item_lines: List[str] = field(default_factory=list)

    # 後方互換用の文字列行（formatter のフォールバック用）
    connection_lines: List[str] = field(default_factory=list)
    sub_location_lines: List[str] = field(default_factory=list)
    object_lines: List[str] = field(default_factory=list)
