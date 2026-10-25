"""本番の現在状態問い合わせは入力条件を検証し、指定値を保持する。"""

import pytest

from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)


class TestGetPlayerCurrentStateQueryValidation:
    """現在状態の問い合わせは正のプレイヤー ID を受け取り、移動先取得の有無を指定できる。"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        """プレイヤー ID が 0 なら ValueError で拒否する。"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetPlayerCurrentStateQuery(player_id=0)

    def test_query_accepts_positive_player_id_and_defaults(self):
        """正のプレイヤー ID を渡すと、移動先を取得する問い合わせになる。"""
        q = GetPlayerCurrentStateQuery(player_id=1)
        assert q.player_id == 1
        assert q.include_available_moves is True

    def test_query_accepts_custom_include_available_moves(self):
        """移動先取得を無効にすると、問い合わせはその指定を保持する。"""
        q = GetPlayerCurrentStateQuery(player_id=1, include_available_moves=False)
        assert q.include_available_moves is False
