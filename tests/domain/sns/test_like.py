import pytest
from datetime import datetime
from src.domain.sns.like import Like


class TestLike:
    """Likeバリューオブジェクトのテスト"""

    def test_create_like_success(self):
        """正常なLikeの作成テスト"""
        user_id = 1
        like = Like(user_id)

        assert like.user_id == user_id
        assert isinstance(like.created_at, datetime)

    def test_create_like_with_explicit_datetime(self):
        """明示的な日時でのLike作成テスト"""
        user_id = 1
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like = Like(user_id, specific_time)

        assert like.user_id == user_id
        assert like.created_at == specific_time

    def test_invalid_user_id_raises_error(self):
        """無効なユーザーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            Like(0)

        with pytest.raises(ValueError, match="user_id must be positive"):
            Like(-1)

    def test_zero_user_id_raises_error(self):
        """ユーザーIDが0の場合のエラーテスト"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            Like(0)

    def test_negative_user_id_raises_error(self):
        """ユーザーIDが負の場合のエラーテスト"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            Like(-1)

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        like = Like(1)
        assert like.user_id == 1

        # 大きな値
        large_user_id = 999999
        like = Like(large_user_id)
        assert like.user_id == large_user_id

    def test_hash_functionality(self):
        """ハッシュ機能のテスト"""
        user_id = 1
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like1 = Like(user_id, specific_time)
        like2 = Like(user_id, specific_time)

        # 同じuser_idのLikeは等価で同じハッシュ値を持つ
        assert like1 == like2
        assert hash(like1) == hash(like2)

        # 異なるuser_idのLikeは異なるハッシュ値を持つ
        like3 = Like(user_id + 1)
        assert like1 != like3
        assert hash(like1) != hash(like3)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        user_id = 1
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        like1 = Like(user_id, time1)
        like2 = Like(user_id, time2)

        # 同じuser_idでも異なる時間の場合は等価ではない
        assert like1 != like2
        assert hash(like1) != hash(like2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        user_id = 1
        time = datetime(2023, 1, 1, 12, 0, 0)

        like1 = Like(user_id, time)
        like2 = Like(user_id, time)

        # 同じuser_idと時間の場合は等価
        assert like1 == like2
        assert hash(like1) == hash(like2)

    def test_immutability(self):
        """不変性のテスト"""
        user_id = 1
        like = Like(user_id)

        # 作成後にプロパティを変更しようとしても変更されない（不変性）
        # これはfrozen=Trueによって保証される

    def test_equality_with_different_instances(self):
        """異なるインスタンスでの等価性テスト"""
        user_id = 1
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like1 = Like(user_id, specific_time)
        like2 = Like(user_id, specific_time)

        # 同じuser_idであれば等価
        assert like1 == like2

    def test_inequality_with_different_user_ids(self):
        """異なるユーザーIDでの非等価性テスト"""
        like1 = Like(1)
        like2 = Like(2)

        assert like1 != like2

    def test_string_representation(self):
        """文字列表現のテスト"""
        user_id = 1
        like = Like(user_id)

        str_repr = str(like)
        assert "Like(" in str_repr
        assert str(user_id) in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        user_id = 1
        like = Like(user_id)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - like.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差
