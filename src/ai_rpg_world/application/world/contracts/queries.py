"""ワールド関連のクエリオブジェクト（読み取り専用）"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetPlayerLocationQuery:
    """プレイヤー位置取得クエリ"""

    player_id: int

    def __post_init__(self):
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
