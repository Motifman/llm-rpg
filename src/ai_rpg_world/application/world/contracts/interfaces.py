"""ワールド・移動まわりのポート（インターフェース）"""

from typing import Protocol

from ai_rpg_world.application.world.contracts.commands import CancelMovementCommand


class ICancelMovementPort(Protocol):
    """経路キャンセルを実行するポート。MovementInterruptionService が breaks_movement 時に使用。"""

    def cancel_movement(self, command: CancelMovementCommand) -> object:
        """指定プレイヤーの経路をキャンセルする。戻り値は実装依存（呼び出し側では無視）。"""
        ...
