"""本番の現在状態問い合わせは入力条件を検証し、指定値を保持する。"""

import pytest

from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)


class TestGetPlayerCurrentStateQueryValidation:
    """現在状態の問い合わせは正のプレイヤー ID を受け取り、0以下を拒否する。"""

    @pytest.mark.parametrize("player_id", [0, -1])
    def test_query_raises_value_error_for_nonpositive_player_id(self, player_id):
        """プレイヤー ID が0以下なら ValueError で拒否する。"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerCurrentStateQuery(player_id=player_id)

    def test_query_accepts_positive_player_id(self):
        """正のプレイヤー ID を渡すと、問い合わせがその ID を保持する。"""
        q = GetPlayerCurrentStateQuery(player_id=1)
        assert q.player_id == 1
