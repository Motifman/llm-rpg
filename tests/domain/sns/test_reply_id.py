import pytest

from ai_rpg_world.domain.sns.exception import ReplyIdValidationException
from ai_rpg_world.domain.sns.value_object import NotificationId, PostId, ReplyId, UserId


class TestReplyId:
    """ReplyIdバリューオブジェクトのテスト"""

    def test_create_reply_id_from_int_string_success(self):
        """整数からの公開生成は値123を持つReplyIdを返す。"""
        reply_id = ReplyId.create(123)
        assert reply_id.value == 123
        assert reply_id == ReplyId(123)

    def test_invalid_reply_id_zero_raises_error(self):
        """返信IDが0の場合のエラーテスト"""
        with pytest.raises(ReplyIdValidationException):
            ReplyId(0)

    def test_invalid_reply_id_string_raises_error(self):
        """無効な文字列からのReplyId作成エラーテスト"""
        with pytest.raises(ReplyIdValidationException):
            ReplyId.create("invalid")

    def test_boundary_reply_id_values(self):
        """境界値の返信IDテスト"""
        # 最小値（1）
        reply_id = ReplyId(1)
        assert reply_id.value == 1
        assert isinstance(reply_id.value, int)
        assert reply_id.value > 0

        # 大きな値
        large_reply_id = 999999
        reply_id = ReplyId(large_reply_id)
        assert reply_id.value == large_reply_id
        assert isinstance(reply_id.value, int)
        assert reply_id.value > 0

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        reply_id1 = ReplyId(1)
        reply_id2 = ReplyId(1)
        reply_id3 = ReplyId(2)

        assert reply_id1 == reply_id2
        assert reply_id1 != reply_id3

    def test_string_representation(self):
        """文字列表現のテスト"""
        reply_id = ReplyId(123)
        assert str(reply_id) == "123"
        assert int(reply_id) == 123

    def test_immutability(self):
        """公開valueへの再代入を拒否し、元のIDを保持する。"""
        reply_id = ReplyId(1)
        with pytest.raises(AttributeError):
            reply_id.value = 2
        assert reply_id.value == 1

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        reply_id1 = ReplyId(1)
        reply_id2 = ReplyId(1)
        reply_id3 = ReplyId(2)

        # 同じ値のReplyIdは同じハッシュ値を持つ
        assert hash(reply_id1) == hash(reply_id2)

        # セットや辞書のキーとして使用可能
        reply_id_set = {reply_id1, reply_id2, reply_id3}
        assert len(reply_id_set) == 2  # reply_id1とreply_id2は同じ

    def test_comparison_with_non_reply_id(self):
        """ReplyId以外との比較テスト"""
        reply_id = ReplyId(1)

        assert reply_id != "1"
        assert reply_id != 1
        assert reply_id != None
        assert reply_id != PostId(1)
        assert reply_id != UserId(1)
        assert reply_id != NotificationId(1)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("123", 123), ("00123", 123), ("999999", 999999)],
    )
    def test_create_from_various_string_formats(self, value, expected):
        """通常・0埋め・大きな整数の文字列から、同じ型の数値IDを返す。"""
        reply_id = ReplyId.create(value)
        assert reply_id.value == expected
        assert reply_id == ReplyId(expected)

    def test_error_message_contains_value(self):
        """エラーメッセージに値が含まれることを確認"""
        with pytest.raises(ReplyIdValidationException) as exc_info:
            ReplyId(-1)

        # エラーメッセージに無効な値が含まれることを確認
        assert str(-1) in str(exc_info.value)
