"""共有の問い合わせと注意水準命令は入力条件を検証し、指定値を保持する。"""

import pytest

from ai_rpg_world.application.world.contracts.commands import ChangeAttentionLevelCommand
from ai_rpg_world.application.world.contracts.queries import (
    GetAvailableMovesQuery,
    GetPlayerCurrentStateQuery,
    GetPlayerLocationQuery,
    GetSpotContextForPlayerQuery,
    GetVisibleContextQuery,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


class TestGetPlayerLocationQueryValidation:
    """現在地の問い合わせは正のplayer_idだけを受け付ける。"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetPlayerLocationQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetPlayerLocationQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self):
        """player_id が正の場合、Query は正常に作成できること"""
        query = GetPlayerLocationQuery(player_id=1)
        assert query.player_id == 1


class TestGetSpotContextForPlayerQueryValidation:
    """周辺情報の問い合わせは正のplayer_idだけを受け付ける。"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetSpotContextForPlayerQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetSpotContextForPlayerQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self):
        """player_id が正の場合、Query は正常に作成できること"""
        query = GetSpotContextForPlayerQuery(player_id=1)
        assert query.player_id == 1


class TestGetAvailableMovesQueryValidation:
    """移動先の問い合わせは正のplayer_idだけを受け付ける。"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetAvailableMovesQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetAvailableMovesQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self):
        """player_id が正の場合、Query は正常に作成できること"""
        query = GetAvailableMovesQuery(player_id=1)
        assert query.player_id == 1


class TestGetVisibleContextQueryValidation:
    """視界の問い合わせは正のplayer_idと0以上の距離を受け付ける。"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetVisibleContextQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            GetVisibleContextQuery(player_id=-1)

    def test_query_raises_value_error_for_negative_distance(self):
        """distance が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match='distance must be 0 or greater'):
            GetVisibleContextQuery(player_id=1, distance=-1)

    def test_query_accepts_positive_player_id_and_default_distance(self):
        """player_id が正の場合、Query は正常に作成でき、distance はデフォルト 5 となること"""
        query = GetVisibleContextQuery(player_id=1)
        assert query.player_id == 1
        assert query.distance == 5

    def test_query_accepts_custom_distance(self):
        """distance を指定した場合、その値が使用されること"""
        query = GetVisibleContextQuery(player_id=1, distance=10)
        assert query.player_id == 1
        assert query.distance == 10


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


class TestChangeAttentionLevelCommandValidation:
    """注意水準の変更命令は正のplayer_idと列挙値だけを受け付ける。"""

    def test_command_raises_value_error_for_invalid_player_id_zero(self):
        """player_id が0なら ValueError で拒否する。"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            ChangeAttentionLevelCommand(player_id=0, attention_level=AttentionLevel.FULL)

    def test_command_raises_value_error_for_negative_player_id(self):
        """player_id が負なら ValueError で拒否する。"""
        with pytest.raises(ValueError, match='player_id must be greater than 0'):
            ChangeAttentionLevelCommand(player_id=-1, attention_level=AttentionLevel.FULL)

    def test_command_raises_value_error_when_attention_level_not_enum(self):
        """注意水準が列挙値でなければ ValueError で拒否する。"""
        with pytest.raises(ValueError, match='attention_level must be an AttentionLevel enum'):
            ChangeAttentionLevelCommand(player_id=1, attention_level='FULL')

    def test_command_accepts_valid_player_id_and_attention_level(self):
        """正のplayer_idと注意水準を指定すると、命令はその値を保持する。"""
        cmd = ChangeAttentionLevelCommand(player_id=1, attention_level=AttentionLevel.IGNORE)
        assert cmd.player_id == 1
        assert cmd.attention_level == AttentionLevel.IGNORE
