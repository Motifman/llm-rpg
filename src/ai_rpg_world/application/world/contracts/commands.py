from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


@dataclass(frozen=True)
class MoveTileCommand:
    """タイルベースの移動コマンド（人間プレイヤー用）"""
    player_id: int
    direction: DirectionEnum
    
    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class SetDestinationCommand:
    """目的地設定コマンド（LLMエージェントまたは自動移動用）"""
    player_id: int
    target_spot_id: int
    target_x: int
    target_y: int
    target_z: int = 0
    
    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.target_spot_id <= 0:
            raise ValueError("target_spot_id must be greater than 0")


@dataclass(frozen=True)
class TickMovementCommand:
    """ティックごとの移動実行コマンド"""
    player_id: int
    
    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetPlayerLocationCommand:
    """プレイヤー位置取得コマンド"""
    player_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetSpotInfoCommand:
    """スポット情報取得コマンド"""
    spot_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.spot_id <= 0:
            raise ValueError("spot_id must be greater than 0")
