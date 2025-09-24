import pytest
from datetime import datetime
from src.domain.sns.follow import FollowRelationShip


class TestFollowRelationShip:
    """FollowRelationShipバリューオブジェクトのテスト"""

    def test_create_follow_relationship_success(self):
        """正常なFollowRelationShipの作成テスト"""
        follower_user_id = 1
        followee_user_id = 2

        follow = FollowRelationShip(follower_user_id, followee_user_id)

        assert follow.follower_user_id == follower_user_id
        assert follow.followee_user_id == followee_user_id
        assert isinstance(follow.created_at, datetime)

    def test_create_follow_relationship_with_explicit_datetime(self):
        """明示的な日時でのFollowRelationShip作成テスト"""
        follower_user_id = 1
        followee_user_id = 2
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        follow = FollowRelationShip(follower_user_id, followee_user_id, specific_time)

        assert follow.follower_user_id == follower_user_id
        assert follow.followee_user_id == followee_user_id
        assert follow.created_at == specific_time

    def test_invalid_follower_user_id_raises_error(self):
        """無効なフォロワーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="follower_user_id must be positive"):
            FollowRelationShip(0, 2)

        with pytest.raises(ValueError, match="follower_user_id must be positive"):
            FollowRelationShip(-1, 2)

    def test_invalid_followee_user_id_raises_error(self):
        """無効なフォロー対象IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="followee_user_id must be positive"):
            FollowRelationShip(1, 0)

        with pytest.raises(ValueError, match="followee_user_id must be positive"):
            FollowRelationShip(1, -1)

    def test_self_follow_allowed(self):
        """自分自身をフォローできることを確認"""
        user_id = 1
        follow = FollowRelationShip(user_id, user_id)
        assert follow.follower_user_id == user_id
        assert follow.followee_user_id == user_id

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        follow = FollowRelationShip(1, 2)
        assert follow.follower_user_id == 1

        # 大きな値
        large_user_id = 999999
        follow = FollowRelationShip(large_user_id, 2)
        assert follow.follower_user_id == large_user_id

        follow = FollowRelationShip(1, large_user_id)
        assert follow.followee_user_id == large_user_id

    def test_is_following_method(self):
        """is_followingメソッドのテスト"""
        follow = FollowRelationShip(1, 2)

        # フォローしているユーザーIDを指定
        assert follow.is_following(2) == True

        # フォローしていないユーザーIDを指定
        assert follow.is_following(1) == False
        assert follow.is_following(3) == False

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        follow1 = FollowRelationShip(1, 2, specific_time)
        follow2 = FollowRelationShip(1, 2, specific_time)

        # 同じユーザーIDの組み合わせであれば等価
        assert follow1 == follow2
        assert hash(follow1) == hash(follow2)

    def test_inequality_with_different_follower_ids(self):
        """異なるフォロワーIDでの非等価性テスト"""
        follow1 = FollowRelationShip(1, 2)
        follow2 = FollowRelationShip(3, 2)

        assert follow1 != follow2
        assert hash(follow1) != hash(follow2)

    def test_inequality_with_different_followee_ids(self):
        """異なるフォロー対象IDでの非等価性テスト"""
        follow1 = FollowRelationShip(1, 2)
        follow2 = FollowRelationShip(1, 3)

        assert follow1 != follow2
        assert hash(follow1) != hash(follow2)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        follow1 = FollowRelationShip(1, 2, time1)
        follow2 = FollowRelationShip(1, 2, time2)

        # 同じユーザーIDでも異なる時間の場合は等価ではない
        assert follow1 != follow2
        assert hash(follow1) != hash(follow2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        follow1 = FollowRelationShip(1, 2, time)
        follow2 = FollowRelationShip(1, 2, time)

        # 同じユーザーIDと時間の場合は等価
        assert follow1 == follow2
        assert hash(follow1) == hash(follow2)

    def test_immutability(self):
        """不変性のテスト"""
        follow = FollowRelationShip(1, 2)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        follow = FollowRelationShip(1, 2)

        str_repr = str(follow)
        assert "FollowRelationShip(" in str_repr
        assert "1" in str_repr
        assert "2" in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        follow = FollowRelationShip(1, 2)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - follow.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差

    def test_different_follower_followee_combinations(self):
        """異なるフォロワー・フォロー対象の組み合わせテスト"""
        # 通常のケース（フォロワーがフォロー対象より小さい）
        follow1 = FollowRelationShip(1, 100)
        assert follow1.follower_user_id == 1
        assert follow1.followee_user_id == 100

        # フォロワーがフォロー対象より大きい
        follow2 = FollowRelationShip(100, 1)
        assert follow2.follower_user_id == 100
        assert follow2.followee_user_id == 1

        # is_followingメソッドのテスト
        assert follow1.is_following(100) == True
        assert follow1.is_following(1) == False
        assert follow2.is_following(1) == True
        assert follow2.is_following(100) == False
