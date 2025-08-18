from dataclasses import dataclass


@dataclass(frozen=True)
class MovePlayerCommand:
    """プレイヤー移動コマンド"""
    player_id: int
    to_spot_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.to_spot_id <= 0:
            raise ValueError("to_spot_id must be greater than 0")


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
