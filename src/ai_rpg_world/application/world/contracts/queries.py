"""ワールド関連のクエリオブジェクト（読み取り専用）"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetPlayerCurrentStateQuery:
    """プレイヤーの現在状態（位置・スポット・天気・地形・視界・移動先・注意レベル）を一括取得するクエリ"""

    player_id: int
    include_available_moves: bool = True

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
