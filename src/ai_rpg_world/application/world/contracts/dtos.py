from dataclasses import dataclass
from typing import List, Set, Optional
from datetime import datetime


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
