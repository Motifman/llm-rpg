"""経路キャンセルの命令が入力規則を守ることを保証する。"""

import pytest

from ai_rpg_world.application.world.contracts.commands import CancelMovementCommand


class TestCancelMovementCommandValidation:
    """CancelMovementCommand は無効なプレイヤーIDを拒否する。"""

    def test_cancel_movement_command_player_id_invalid_raises(self):
        """CancelMovementCommand の player_id が 0 以下の場合 ValueError"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            CancelMovementCommand(player_id=0)
