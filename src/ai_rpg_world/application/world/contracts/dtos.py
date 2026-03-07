from dataclasses import dataclass, field
from typing import List, Set, Optional
from datetime import datetime

from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


@dataclass
class PlayerLocationDto:
    """プレイヤー位置DTO"""
    player_id: int
    player_name: str
    current_spot_id: int
    current_spot_name: str
    current_spot_description: str
    x: int
    y: int
    z: int
    area_id: Optional[int]
    area_name: Optional[str]


@dataclass
class SpotInfoDto:
    """スポット情報DTO"""
    spot_id: int
    name: str
    description: str
    area_id: Optional[int]
    area_name: Optional[str]
    current_player_count: int
    current_player_ids: Set[int]
    connected_spot_ids: Set[int]
    connected_spot_names: Set[str]


@dataclass
class VisibleObjectDto:
    """視界内オブジェクト1件のDTO"""
    object_id: int
    object_type: str
    x: int
    y: int
    z: int
    distance: int
    display_name: Optional[str] = None
    object_kind: Optional[str] = None
    direction_from_player: Optional[str] = None
    is_interactable: bool = False
    player_id_value: Optional[int] = None
    is_self: bool = False
    interaction_type: Optional[str] = None
    available_interactions: List[str] = field(default_factory=list)
    can_interact: bool = False
    can_harvest: bool = False
    can_store_in_chest: bool = False
    can_take_from_chest: bool = False


@dataclass
class VisibleContextDto:
    """プレイヤー視点の視界内コンテキストDTO"""
    player_id: int
    player_name: str
    spot_id: int
    spot_name: str
    center_x: int
    center_y: int
    center_z: int
    view_distance: int
    visible_objects: List["VisibleObjectDto"]


@dataclass
class MoveResultDto:
    """移動結果DTO"""
    success: bool
    player_id: int
    player_name: str
    from_spot_id: int
    from_spot_name: str
    to_spot_id: int
    to_spot_name: str
    from_coordinate: dict # {"x": x, "y": y, "z": z}
    to_coordinate: dict
    moved_at: datetime
    busy_until_tick: int
    message: str
    error_message: Optional[str] = None


@dataclass
class AvailableMoveDto:
    """利用可能な移動先DTO"""
    spot_id: int
    spot_name: str
    road_id: int
    road_description: str
    conditions_met: bool
    failed_conditions: List[str]


@dataclass
class PlayerMovementOptionsDto:
    """プレイヤーの移動オプションDTO"""
    player_id: int
    player_name: str
    current_spot_id: int
    current_spot_name: str
    available_moves: List[AvailableMoveDto]
    total_available_moves: int


@dataclass
class InventoryItemDto:
    """インベントリ内アイテム 1 件の DTO"""

    inventory_slot_id: int
    item_instance_id: int
    display_name: str
    quantity: int
    is_placeable: bool = False


@dataclass
class ChestItemDto:
    """チェスト内アイテム 1 件の DTO"""

    chest_world_object_id: int
    chest_display_name: str
    item_instance_id: int
    display_name: str
    quantity: int


@dataclass
class ConversationChoiceDto:
    """会話の選択肢または次へ操作の DTO"""

    display_text: str
    choice_index: Optional[int] = None
    is_next: bool = False


@dataclass
class ActiveConversationDto:
    """現在進行中の会話セッション DTO"""

    npc_world_object_id: int
    npc_display_name: str
    node_text: str
    choices: List[ConversationChoiceDto]
    is_terminal: bool


@dataclass
class UsableSkillDto:
    """使用可能スキル 1 件の DTO"""

    skill_loadout_id: int
    skill_slot_index: int
    skill_id: int
    display_name: str
    mp_cost: int = 0
    stamina_cost: int = 0
    hp_cost: int = 0


@dataclass
class AttentionLevelOptionDto:
    """選択可能な注意レベル DTO"""

    value: str
    display_name: str
    description: str


@dataclass
class PlayerCurrentStateDto:
    """
    LLM 入力用の単一「現在状態」DTO。
    プレイヤー位置・スポット周辺・天気・地形・視界内オブジェクト・利用可能な移動先・注意レベルをまとめて保持する。
    """
    # プレイヤー識別
    player_id: int
    player_name: str
    # 現在地
    current_spot_id: Optional[int]
    current_spot_name: Optional[str]
    current_spot_description: Optional[str]
    x: Optional[int]
    y: Optional[int]
    z: Optional[int]
    area_id: Optional[int]
    area_name: Optional[str]
    # スポット周辺（同スポット他プレイヤー・接続先）
    current_player_count: int
    current_player_ids: Set[int]
    connected_spot_ids: Set[int]
    connected_spot_names: Set[str]
    # 天気（現在スポット）
    weather_type: str
    weather_intensity: float
    # 現在タイルの地形
    current_terrain_type: Optional[str]
    # 視界内オブジェクト
    visible_objects: List[VisibleObjectDto]
    view_distance: int
    # 利用可能な移動先（オプション）
    available_moves: Optional[List[AvailableMoveDto]]
    total_available_moves: Optional[int]
    # 注意レベル
    attention_level: AttentionLevel
    # 複数ティックの行動中か（経路設定済みの移動中など）。割り込み判定に利用。
    is_busy: bool = False
    busy_until_tick: Optional[int] = None
    has_active_path: bool = False
    # sibling-list UI context
    inventory_items: List[InventoryItemDto] = field(default_factory=list)
    chest_items: List[ChestItemDto] = field(default_factory=list)
    active_conversation: Optional[ActiveConversationDto] = None
    usable_skills: List[UsableSkillDto] = field(default_factory=list)
    attention_level_options: List[AttentionLevelOptionDto] = field(default_factory=list)
    can_destroy_placeable: bool = False
