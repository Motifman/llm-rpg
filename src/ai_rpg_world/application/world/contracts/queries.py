"""ワールド関連のクエリオブジェクト（読み取り専用）"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetPlayerCurrentStateQuery:
    """プレイヤーのスポット状態を取得する問い合わせ。"""

    player_id: int

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
