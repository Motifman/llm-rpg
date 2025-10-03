import pytest
from src.domain.sns.value_object import UserId
from src.domain.sns.exception import UserIdValidationException


class TestUserId:
    """UserIdバリューオブジェクトのテスト"""

    def test_create_user_id_success(self):
        """正常なUserIdの作成テスト"""
        user_id = UserId(1)
        assert user_id.value == 1

    def test_create_user_id_from_string_success(self):
        """文字列からのUserId作成テスト"""
        user_id = UserId.create("123")
        assert user_id.value == 123
        assert user_id == UserId(123)

    def test_create_user_id_from_int_string_success(self):
        """int文字列からのUserId作成テスト"""
        user_id = UserId.create(123)
        assert user_id.value == 123

    def test_invalid_user_id_zero_raises_error(self):
        """ユーザーIDが0の場合のエラーテスト"""
        with pytest.raises(UserIdValidationException):
            UserId(0)

    def test_invalid_user_id_negative_raises_error(self):
        """ユーザーIDが負の場合のエラーテスト"""
        with pytest.raises(UserIdValidationException):
            UserId(-1)

    def test_invalid_user_id_string_raises_error(self):
        """無効な文字列からのUserId作成エラーテスト"""
        with pytest.raises(UserIdValidationException):
            UserId.create("invalid")

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        user_id = UserId(1)
        assert user_id.value == 1

        # 大きな値
        large_user_id = 999999
        user_id = UserId(large_user_id)
        assert user_id.value == large_user_id

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        user_id1 = UserId(1)
        user_id2 = UserId(1)
        user_id3 = UserId(2)

        assert user_id1 == user_id2
        assert user_id1 != user_id3
        assert hash(user_id1) == hash(user_id2)
        assert hash(user_id1) != hash(user_id3)

    def test_string_representation(self):
        """文字列表現のテスト"""
        user_id = UserId(123)
        assert str(user_id) == "123"
        assert int(user_id) == 123

    def test_immutability(self):
        """不変性のテスト"""
        user_id = UserId(1)
        # frozen=Trueにより不変性を保証

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        user_id1 = UserId(1)
        user_id2 = UserId(1)
        user_id3 = UserId(2)

        # 同じ値のUserIdは同じハッシュ値を持つ
        assert hash(user_id1) == hash(user_id2)
        assert hash(user_id1) != hash(user_id3)

        # セットや辞書のキーとして使用可能
        user_id_set = {user_id1, user_id2, user_id3}
        assert len(user_id_set) == 2  # user_id1とuser_id2は同じ

    def test_comparison_with_non_user_id(self):
        """UserId以外との比較テスト"""
        user_id = UserId(1)

        assert user_id != "1"
        assert user_id != 1
        assert user_id != None

    def test_create_from_various_string_formats(self):
        """様々な文字列形式からの作成テスト"""
        # 通常の文字列
        assert UserId.create("123").value == 123

        # 0埋め文字列
        assert UserId.create("00123").value == 123

        # 最大値文字列
        assert UserId.create("999999").value == 999999

    def test_error_message_contains_value(self):
        """エラーメッセージに値が含まれることを確認"""
        with pytest.raises(UserIdValidationException) as exc_info:
            UserId(-1)

        # エラーメッセージに無効な値が含まれることを確認
        assert str(-1) in str(exc_info.value)

    def test_type_safety(self):
        """型安全性のテスト"""
        user_id = UserId(1)

        # 型ヒントによる安全性（実行時エラーではないが、IDEでの支援を確認）
        assert isinstance(user_id.value, int)
        assert user_id.value > 0
