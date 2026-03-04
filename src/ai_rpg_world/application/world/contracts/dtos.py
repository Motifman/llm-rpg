from dataclasses import dataclass
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
