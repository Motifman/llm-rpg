from dataclasses import dataclass


@dataclass(frozen=True)
class CancelMovementCommand:
    """経路をキャンセルするコマンド（割り込み時など）。目的地設定を解除し、行動中フラグをクリアする。"""
    player_id: int

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
