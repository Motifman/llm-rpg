"""スポットグラフ用の現在状態スナップショット（LLM プロンプト向け）"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# --- 構造化エントリ（UiContextBuilder がラベル付与に使用） ---

@dataclass(frozen=True)
class SpotGraphInteractionEntry:
    action_name: str
    display_label: str


@dataclass(frozen=True)
class SpotGraphConnectionEntry:
    """接続先1件の構造化データ。

    注: フィールド名 `is_passable` は LLM プロンプト・WebSocket/REST レスポンスで
    使われている外部互換のフィールド名なので、ドメイン側の `passage.traversable`
    とは意図的に名前を分けている（リネームすると外部契約が壊れるため温存）。
    """
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
    # Phase 4-E: スポット内オブジェクトの可観測な state 値 (扉が開いている、
    # 燭台が点いている など)。プロンプト現在状態に「燭台: lit=True」のように
    # 載せるための入力。スポットに居る全員から見える前提なので絞り込みは無し。
    state: Dict[str, Any] = field(default_factory=dict)


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
    perception_note: Optional[str] = None  # 照明知覚の補足テキスト


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

    # エージェントの欲求状態テキスト
    need_lines: Tuple[str, ...] = ()

    # Phase 4-E: 行動者本人の自由 state (HIDDEN を含む全項目)。
    # 自分自身の内面なので毒・呪い・隠しフラグも本人プロンプトには載せる。
    # 第三者観測には流れない (formatter は他プレイヤー snapshot を作らない設計)。
    player_state: Dict[str, Any] = field(default_factory=dict)

    # 後方互換用の文字列行（formatter のフォールバック用）
    connection_lines: List[str] = field(default_factory=list)
    sub_location_lines: List[str] = field(default_factory=list)
    object_lines: List[str] = field(default_factory=list)
