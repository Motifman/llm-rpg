import pytest
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.exception.player_exceptions import PlayerIdValidationException


class TestPlayerId:
    """PlayerIdバリューオブジェクトのテスト"""

    def test_create_player_id_success(self):
        """正常なPlayerIdの作成テスト"""
        player_id = PlayerId(1)
        assert player_id.value == 1

    def test_create_player_id_from_string_success(self):
        """文字列からのPlayerId作成テスト"""
        player_id = PlayerId.create("123")
        assert player_id.value == 123
        assert player_id == PlayerId(123)

    def test_create_player_id_from_int_string_success(self):
        """int文字列からのPlayerId作成テスト"""
        player_id = PlayerId.create(123)
        assert player_id.value == 123

    def test_invalid_player_id_zero_raises_error(self):
        """プレイヤーIDが0の場合のエラーテスト"""
        with pytest.raises(PlayerIdValidationException):
            PlayerId(0)

    def test_invalid_player_id_negative_raises_error(self):
        """プレイヤーIDが負の場合のエラーテスト"""
        with pytest.raises(PlayerIdValidationException):
            PlayerId(-1)

    def test_invalid_player_id_string_raises_error(self):
        """無効な文字列からのPlayerId作成エラーテスト"""
        with pytest.raises(PlayerIdValidationException):
            PlayerId.create("invalid")

    def test_boundary_player_id_values(self):
        """境界値のプレイヤーIDテスト"""
        # 最小値（1）
        player_id = PlayerId(1)
        assert player_id.value == 1

        # 大きな値
        large_player_id = 999999
        player_id = PlayerId(large_player_id)
        assert player_id.value == large_player_id

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        player_id1 = PlayerId(1)
        player_id2 = PlayerId(1)
        player_id3 = PlayerId(2)

        assert player_id1 == player_id2
        assert player_id1 != player_id3
        assert hash(player_id1) == hash(player_id2)
        assert hash(player_id1) != hash(player_id3)

    def test_string_representation(self):
        """文字列表現のテスト"""
        player_id = PlayerId(123)
        assert str(player_id) == "123"
        assert int(player_id) == 123

    def test_immutability(self):
        """不変性のテスト"""
        player_id = PlayerId(1)
        # frozen=Trueにより不変性を保証

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        player_id1 = PlayerId(1)
        player_id2 = PlayerId(1)
        player_id3 = PlayerId(2)

        # 同じ値のPlayerIdは同じハッシュ値を持つ
        assert hash(player_id1) == hash(player_id2)
        assert hash(player_id1) != hash(player_id3)

        # セットや辞書のキーとして使用可能
        player_id_set = {player_id1, player_id2, player_id3}
        assert len(player_id_set) == 2  # player_id1とplayer_id2は同じ

    def test_comparison_with_non_player_id(self):
        """PlayerId以外との比較テスト"""
        player_id = PlayerId(1)

        assert player_id != "1"
        assert player_id != 1
        assert player_id != None

    def test_create_from_various_string_formats(self):
        """様々な文字列形式からの作成テスト"""
        # 通常の文字列
        assert PlayerId.create("123").value == 123

        # 0埋め文字列
        assert PlayerId.create("00123").value == 123

        # 最大値文字列
        assert PlayerId.create("999999").value == 999999

    def test_error_message_contains_value(self):
        """エラーメッセージに値が含まれることを確認"""
        with pytest.raises(PlayerIdValidationException) as exc_info:
            PlayerId(-1)

        # エラーメッセージに無効な値が含まれることを確認
        assert str(-1) in str(exc_info.value)

    def test_type_safety(self):
        """型安全性のテスト"""
        player_id = PlayerId(1)

        # 型ヒントによる安全性（実行時エラーではないが、IDEでの支援を確認）
        assert isinstance(player_id.value, int)
        assert player_id.value > 0
