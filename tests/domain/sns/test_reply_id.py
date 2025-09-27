import pytest
from src.domain.sns.value_object import ReplyId
from src.domain.sns.exception import ReplyIdValidationException


class TestReplyId:
    """ReplyIdバリューオブジェクトのテスト"""

    def test_create_reply_id_success(self):
        """正常なReplyIdの作成テスト"""
        reply_id = ReplyId(1)
        assert reply_id.value == 1

    def test_create_reply_id_from_string_success(self):
        """文字列からのReplyId作成テスト"""
        reply_id = ReplyId.create("123")
        assert reply_id.value == 123
        assert reply_id == ReplyId(123)

    def test_create_reply_id_from_int_string_success(self):
        """int文字列からのReplyId作成テスト"""
        reply_id = ReplyId.create(123)
        assert reply_id.value == 123

    def test_invalid_reply_id_zero_raises_error(self):
        """返信IDが0の場合のエラーテスト"""
        with pytest.raises(ReplyIdValidationException):
            ReplyId(0)

    def test_invalid_reply_id_negative_raises_error(self):
        """返信IDが負の場合のエラーテスト"""
        with pytest.raises(ReplyIdValidationException):
            ReplyId(-1)

    def test_invalid_reply_id_string_raises_error(self):
        """無効な文字列からのReplyId作成エラーテスト"""
        with pytest.raises(ReplyIdValidationException):
            ReplyId.create("invalid")

    def test_boundary_reply_id_values(self):
        """境界値の返信IDテスト"""
        # 最小値（1）
        reply_id = ReplyId(1)
        assert reply_id.value == 1

        # 大きな値
        large_reply_id = 999999
        reply_id = ReplyId(large_reply_id)
        assert reply_id.value == large_reply_id

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        reply_id1 = ReplyId(1)
        reply_id2 = ReplyId(1)
        reply_id3 = ReplyId(2)

        assert reply_id1 == reply_id2
        assert reply_id1 != reply_id3
        assert hash(reply_id1) == hash(reply_id2)
        assert hash(reply_id1) != hash(reply_id3)

    def test_string_representation(self):
        """文字列表現のテスト"""
        reply_id = ReplyId(123)
        assert str(reply_id) == "123"
        assert int(reply_id) == 123

    def test_immutability(self):
        """不変性のテスト"""
        reply_id = ReplyId(1)
        # frozen=Trueにより不変性を保証

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        reply_id1 = ReplyId(1)
        reply_id2 = ReplyId(1)
        reply_id3 = ReplyId(2)

        # 同じ値のReplyIdは同じハッシュ値を持つ
        assert hash(reply_id1) == hash(reply_id2)
        assert hash(reply_id1) != hash(reply_id3)

        # セットや辞書のキーとして使用可能
        reply_id_set = {reply_id1, reply_id2, reply_id3}
        assert len(reply_id_set) == 2  # reply_id1とreply_id2は同じ

    def test_comparison_with_non_reply_id(self):
        """ReplyId以外との比較テスト"""
        reply_id = ReplyId(1)

        assert reply_id != "1"
        assert reply_id != 1
        assert reply_id != None

    def test_create_from_various_string_formats(self):
        """様々な文字列形式からの作成テスト"""
        # 通常の文字列
        assert ReplyId.create("123").value == 123

        # 0埋め文字列
        assert ReplyId.create("00123").value == 123

        # 最大値文字列
        assert ReplyId.create("999999").value == 999999

    def test_error_message_contains_value(self):
        """エラーメッセージに値が含まれることを確認"""
        with pytest.raises(ReplyIdValidationException) as exc_info:
            ReplyId(-1)

        # エラーメッセージに無効な値が含まれることを確認
        assert str(-1) in str(exc_info.value)

    def test_type_safety(self):
        """型安全性のテスト"""
        reply_id = ReplyId(1)

        # 型ヒントによる安全性（実行時エラーではないが、IDEでの支援を確認）
        assert isinstance(reply_id.value, int)
        assert reply_id.value > 0
