"""スポットグラフ専用ランタイム向けのタイル移動キャンセルスタブ（LlmAgentTurnRunner 契約用）"""

from __future__ import annotations

from datetime import datetime

from ai_rpg_world.application.world.contracts.commands import CancelMovementCommand
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto


class SpotGraphNoOpMovementService:
    """タイルマップ移動がないモードでは cancel_movement を no-op として処理する。"""

    def cancel_movement(self, command: CancelMovementCommand) -> MoveResultDto:
        now = datetime.now()
        return MoveResultDto(
            success=True,
            player_id=command.player_id,
            player_name="",
            from_spot_id=0,
            from_spot_name="",
            to_spot_id=0,
            to_spot_name="",
            from_coordinate={"x": 0, "y": 0, "z": 0},
            to_coordinate={"x": 0, "y": 0, "z": 0},
            moved_at=now,
            busy_until_tick=0,
            message="スポットグラフモード: タイル移動のキャンセルは不要です。",
        )
