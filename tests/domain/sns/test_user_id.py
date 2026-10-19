import pytest

from ai_rpg_world.domain.sns.exception import UserIdValidationException
from ai_rpg_world.domain.sns.value_object import NotificationId, PostId, ReplyId, UserId


class TestUserId:
    """UserIdバリューオブジェクトのテスト"""

    def test_create_user_id_from_int_string_success(self):
        """整数からの公開生成は値123を持つUserIdを返す。"""
        user_id = UserId.create(123)
        assert user_id.value == 123
        assert user_id == UserId(123)

    def test_invalid_user_id_zero_raises_error(self):
        """ユーザーIDが0の場合のエラーテスト"""
        with pytest.raises(UserIdValidationException):
            UserId(0)

    def test_invalid_user_id_string_raises_error(self):
        """無効な文字列からのUserId作成エラーテスト"""
        with pytest.raises(UserIdValidationException):
            UserId.create("invalid")

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        user_id = UserId(1)
        assert user_id.value == 1
        assert isinstance(user_id.value, int)
        assert user_id.value > 0

        # 大きな値
        large_user_id = 999999
        user_id = UserId(large_user_id)
        assert user_id.value == large_user_id
        assert isinstance(user_id.value, int)
        assert user_id.value > 0

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        user_id1 = UserId(1)
        user_id2 = UserId(1)
        user_id3 = UserId(2)

        assert user_id1 == user_id2
        assert user_id1 != user_id3

    def test_string_representation(self):
        """文字列表現のテスト"""
        user_id = UserId(123)
        assert str(user_id) == "123"
        assert int(user_id) == 123

    def test_immutability(self):
        """公開valueへの再代入を拒否し、元のIDを保持する。"""
        user_id = UserId(1)
        with pytest.raises(AttributeError):
            user_id.value = 2
        assert user_id.value == 1

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        user_id1 = UserId(1)
        user_id2 = UserId(1)
        user_id3 = UserId(2)

        # 同じ値のUserIdは同じハッシュ値を持つ
        assert hash(user_id1) == hash(user_id2)

        # セットや辞書のキーとして使用可能
        user_id_set = {user_id1, user_id2, user_id3}
        assert len(user_id_set) == 2  # user_id1とuser_id2は同じ

    def test_comparison_with_non_user_id(self):
        """UserId以外との比較テスト"""
        user_id = UserId(1)

        assert user_id != "1"
        assert user_id != 1
        assert user_id != None
        assert user_id != PostId(1)
        assert user_id != ReplyId(1)
        assert user_id != NotificationId(1)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("123", 123), ("00123", 123), ("999999", 999999)],
    )
    def test_create_from_various_string_formats(self, value, expected):
        """通常・0埋め・大きな整数の文字列から、同じ型の数値IDを返す。"""
        user_id = UserId.create(value)
        assert user_id.value == expected
        assert user_id == UserId(expected)

    def test_error_message_contains_value(self):
        """エラーメッセージに値が含まれることを確認"""
        with pytest.raises(UserIdValidationException) as exc_info:
            UserId(-1)

        # エラーメッセージに無効な値が含まれることを確認
        assert str(-1) in str(exc_info.value)
