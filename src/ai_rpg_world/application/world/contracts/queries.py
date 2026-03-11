"""ワールド関連のクエリオブジェクト（読み取り専用）"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetPlayerLocationQuery:
    """プレイヤー位置取得クエリ"""

    player_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetSpotContextForPlayerQuery:
    """プレイヤー視点の現在スポット情報＋接続先一覧取得クエリ"""

    player_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetVisibleContextQuery:
    """プレイヤー視点の視界内オブジェクト取得クエリ"""

    player_id: int
    distance: int = 5

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.distance < 0:
            raise ValueError("distance must be 0 or greater")


@dataclass(frozen=True)
class GetAvailableMovesQuery:
    """プレイヤーの利用可能な移動先一覧取得クエリ"""

    player_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetPlayerCurrentStateQuery:
    """プレイヤーの現在状態（位置・スポット・天気・地形・視界・移動先・注意レベル）を一括取得するクエリ"""

    player_id: int
    include_available_moves: bool = True
    include_tile_map: bool = True
    view_distance: int = 5

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if self.view_distance < 0:
            raise ValueError("view_distance must be 0 or greater")
