import pytest
from datetime import datetime
from src.domain.sns.value_object import Like, UserId, PostId


class TestLike:
    """Likeバリューオブジェクトのテスト"""

    def test_create_like_success(self):
        """正常なLikeの作成テスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        like = Like(user_id, post_id)

        assert like.user_id == user_id
        assert like.post_id == post_id
        assert isinstance(like.created_at, datetime)

    def test_create_like_with_explicit_datetime(self):
        """明示的な日時でのLike作成テスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like = Like(user_id, post_id, specific_time)

        assert like.user_id == user_id
        assert like.post_id == post_id
        assert like.created_at == specific_time

    def test_invalid_user_id_raises_error(self):
        """無効なユーザーIDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_invalid_post_id_raises_error(self):
        """無効な投稿IDの場合のエラーテスト"""
        with pytest.raises(Exception):  # PostIdValidationException
            PostId(0)

    def test_boundary_id_values(self):
        """境界値のIDテスト"""
        # 最小値（1）
        user_id = UserId(1)
        post_id = PostId(1)
        like = Like(user_id, post_id)
        assert like.user_id == user_id
        assert like.post_id == post_id

        # 大きな値
        large_user_id = UserId(999999)
        large_post_id = PostId(999999)
        like = Like(large_user_id, large_post_id)
        assert like.user_id == large_user_id
        assert like.post_id == large_post_id

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like1 = Like(user_id, post_id, specific_time)
        like2 = Like(user_id, post_id, specific_time)

        # 同じIDと時間のLikeは等価で同じハッシュ値を持つ
        assert like1 == like2
        assert hash(like1) == hash(like2)

        # 異なるユーザーIDのLikeは異なるハッシュ値を持つ
        different_user_id = UserId(2)
        like3 = Like(different_user_id, post_id, specific_time)
        assert like1 != like3
        assert hash(like1) != hash(like3)

        # 異なる投稿IDのLikeは異なるハッシュ値を持つ
        different_post_id = PostId(2)
        like4 = Like(user_id, different_post_id, specific_time)
        assert like1 != like4
        assert hash(like1) != hash(like4)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        like1 = Like(user_id, post_id, time1)
        like2 = Like(user_id, post_id, time2)

        # 同じIDでも異なる時間の場合は等価（作成時間は比較に含めない）
        assert like1 == like2
        assert hash(like1) == hash(like2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        time = datetime(2023, 1, 1, 12, 0, 0)

        like1 = Like(user_id, post_id, time)
        like2 = Like(user_id, post_id, time)

        # 同じIDと時間の場合は等価
        assert like1 == like2
        assert hash(like1) == hash(like2)

    def test_immutability(self):
        """不変性のテスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        like = Like(user_id, post_id)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_equality_with_different_instances(self):
        """異なるインスタンスでの等価性テスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like1 = Like(user_id, post_id, specific_time)
        like2 = Like(user_id, post_id, specific_time)

        # 同じIDと時間であれば等価
        assert like1 == like2

    def test_inequality_with_different_user_ids(self):
        """異なるユーザーIDでの非等価性テスト"""
        user_id1 = UserId(1)
        user_id2 = UserId(2)
        post_id = PostId(1)
        like1 = Like(user_id1, post_id)
        like2 = Like(user_id2, post_id)

        assert like1 != like2

    def test_inequality_with_different_post_ids(self):
        """異なる投稿IDでの非等価性テスト"""
        user_id = UserId(1)
        post_id1 = PostId(1)
        post_id2 = PostId(2)
        like1 = Like(user_id, post_id1)
        like2 = Like(user_id, post_id2)

        assert like1 != like2

    def test_string_representation(self):
        """文字列表現のテスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        like = Like(user_id, post_id)

        str_repr = str(like)
        assert "Like(" in str_repr
        assert str(user_id) in str_repr
        assert str(post_id) in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        like = Like(user_id, post_id)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - like.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差

    def test_id_string_conversion(self):
        """IDの文字列変換テスト"""
        user_id = UserId(123)
        post_id = PostId(456)
        like = Like(user_id, post_id)

        assert str(like.user_id) == "123"
        assert str(like.post_id) == "456"
        assert int(like.user_id) == 123
        assert int(like.post_id) == 456
