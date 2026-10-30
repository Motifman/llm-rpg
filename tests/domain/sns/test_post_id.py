import pytest

from ai_rpg_world.domain.sns.exception import PostIdValidationException
from ai_rpg_world.domain.sns.value_object import NotificationId, PostId, ReplyId, UserId


class TestPostId:
    """PostIdバリューオブジェクトのテスト"""

    def test_create_post_id_from_int_string_success(self):
        """整数からの公開生成は値123を持つPostIdを返す。"""
        post_id = PostId.create(123)
        assert post_id.value == 123
        assert post_id == PostId(123)

    def test_invalid_post_id_zero_raises_error(self):
        """投稿IDが0の場合のエラーテスト"""
        with pytest.raises(PostIdValidationException):
            PostId(0)

    def test_invalid_post_id_string_raises_error(self):
        """無効な文字列からのPostId作成エラーテスト"""
        with pytest.raises(PostIdValidationException):
            PostId.create("invalid")

    def test_boundary_post_id_values(self):
        """境界値の投稿IDテスト"""
        # 最小値（1）
        post_id = PostId(1)
        assert post_id.value == 1
        assert isinstance(post_id.value, int)
        assert post_id.value > 0

        # 大きな値
        large_post_id = 999999
        post_id = PostId(large_post_id)
        assert post_id.value == large_post_id
        assert isinstance(post_id.value, int)
        assert post_id.value > 0

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        post_id1 = PostId(1)
        post_id2 = PostId(1)
        post_id3 = PostId(2)

        assert post_id1 == post_id2
        assert post_id1 != post_id3

    def test_string_representation(self):
        """文字列表現のテスト"""
        post_id = PostId(123)
        assert str(post_id) == "123"
        assert int(post_id) == 123

    def test_immutability(self):
        """公開valueへの再代入を拒否し、元のIDを保持する。"""
        post_id = PostId(1)
        with pytest.raises(AttributeError):
            post_id.value = 2
        assert post_id.value == 1

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        post_id1 = PostId(1)
        post_id2 = PostId(1)
        post_id3 = PostId(2)

        # 同じ値のPostIdは同じハッシュ値を持つ
        assert hash(post_id1) == hash(post_id2)

        # セットや辞書のキーとして使用可能
        post_id_set = {post_id1, post_id2, post_id3}
        assert len(post_id_set) == 2  # post_id1とpost_id2は同じ

    def test_comparison_with_non_post_id(self):
        """PostId以外との比較テスト"""
        post_id = PostId(1)

        assert post_id != "1"
        assert post_id != 1
        assert post_id != None
        assert post_id != ReplyId(1)
        assert post_id != UserId(1)
        assert post_id != NotificationId(1)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("123", 123), ("00123", 123), ("999999", 999999)],
    )
    def test_create_from_various_string_formats(self, value, expected):
        """通常・0埋め・大きな整数の文字列から、同じ型の数値IDを返す。"""
        post_id = PostId.create(value)
        assert post_id.value == expected
        assert post_id == PostId(expected)

    def test_error_message_contains_value(self):
        """エラーメッセージに値が含まれることを確認"""
        with pytest.raises(PostIdValidationException) as exc_info:
            PostId(-1)

        # エラーメッセージに無効な値が含まれることを確認
        assert str(-1) in str(exc_info.value)
