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
class SpotGraphTimeOfDayEntry:
    """現在時刻 (昼夜サイクルの今のフェーズ) の prompt 用構造化データ。

    シナリオが day_night サイクルを宣言していなければ snapshot.time_of_day は
    None。「現在時刻: 朝」のような行をプロンプトに 1 行足すために使う。
    """
    phase_name: str
    display_text: str
    is_dark: bool


@dataclass(frozen=True)
class SpotGraphInventoryItemEntry:
    """所持アイテム1件の構造化データ。

    quantity > 1 のときは spec が同じ複数 instance を集約表示するが、
    LLM tool (drop_item 等) が単体を指せるよう slot_id と item_instance_id
    も保持する。集約時は代表 instance (最初に発見したスロットの instance)
    の id を載せる。-1 は未設定を表す sentinel。
    """
    item_spec_id: int
    name: str
    quantity: int
    # 代表 instance のスロット番号 (drop_item でスロットを直接指す代替手段)
    slot_id: int = -1
    # 代表 instance の ItemInstanceId (drop_item で対象を一意に指せる)
    item_instance_id: int = -1
    # Phase D-3a: 食料腐敗の表示用フラグ。同 spec でも spoiled 状態が異なる
    # instance は別エントリに集約する想定 (「生の魚 x2」と「生の魚 x1 (腐敗)」
    # を並べて表示するため)。default False で既存呼び出し側に無影響。
    is_spoiled: bool = False


@dataclass(frozen=True)
class SpotGraphGroundItemEntry:
    """現在地の地面アイテム1件の構造化データ。

    プレイヤーが drop した、またはモンスター死亡時に落とした、シナリオ
    初期配置で置かれたアイテムを、pickup tool が指せるラベル付きで
    プロンプトに載せるために使う。
    """
    item_instance_id: int
    item_spec_id: int
    name: str
    # Phase D-3a: 地面に落ちている食料も腐敗する。表示用フラグ。default False。
    is_spoiled: bool = False


@dataclass(frozen=True)
class SpotGraphNearbyEntityEntry:
    """同スポットにいるエンティティ1件の構造化データ。"""
    entity_id: int
    display_name: str = ""


@dataclass(frozen=True)
class SpotGraphMonsterEntry:
    """同スポットに居るモンスター個体1件の構造化データ。

    LLM プロンプトに「灰色のオオカミ（敵対的・弱っている）」のような形で
    載せ、ラベル付与（M1, M2 等）と targeting に使う。

    可視化方針:
    - `display_name`: モンスターテンプレート名（種族名）
    - `behavior_label`: idle/alert/hostile/fleeing 等を日本語化した短い表記
    - `health_bucket`: 数値 HP は隠し、`healthy`/`wounded`/`dying` の 3 段階に丸める。
      現実世界での観測（姿勢・出血・荒い呼吸）に近づける狙い
    - `is_dead`: 死体の場合に True。生存個体とは表記を分ける
    """

    monster_id: int
    display_name: str
    behavior_label: str
    health_bucket: str
    is_dead: bool = False


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
    # 現在時刻 (昼夜フェーズ) — シナリオが day_night を宣言していなければ None
    time_of_day: Optional[SpotGraphTimeOfDayEntry] = None
    nearby_entities: Tuple[SpotGraphNearbyEntityEntry, ...] = ()
    monsters_at_spot: Tuple[SpotGraphMonsterEntry, ...] = ()
    inventory_items: Tuple[SpotGraphInventoryItemEntry, ...] = ()
    # 現在地の地面に落ちているアイテム (drop された / モンスター死亡時ドロップ /
    # シナリオ初期配置)。pickup tool が G1, G2 ... ラベルで指せるよう
    # 構造化して保持する。
    ground_items: Tuple[SpotGraphGroundItemEntry, ...] = ()
    ground_item_lines: List[str] = field(default_factory=list)

    # エージェントの欲求状態テキスト
    need_lines: Tuple[str, ...] = ()

    # PR #2 状態異常: 適用中の StatusEffect を読みやすい文字列行に変換したもの。
    # 「出血 (残り 9 tick)」のような表記で LLM に渡し、bandage を探す行動連鎖を
    # 取れるようにする。effects が空のときは () を返す。
    active_effect_lines: Tuple[str, ...] = ()

    # Phase 4-E: 行動者本人の自由 state (HIDDEN を含む全項目)。
    # 自分自身の内面なので毒・呪い・隠しフラグも本人プロンプトには載せる。
    # 第三者観測には流れない (formatter は他プレイヤー snapshot を作らない設計)。
    player_state: Dict[str, Any] = field(default_factory=dict)

    # 後方互換用の文字列行（formatter のフォールバック用）
    connection_lines: List[str] = field(default_factory=list)
    sub_location_lines: List[str] = field(default_factory=list)
    object_lines: List[str] = field(default_factory=list)
