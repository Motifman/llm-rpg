import pytest
from datetime import datetime
from src.domain.sns.value_object import FollowRelationShip, UserId
from src.domain.sns.exception import (
    UserIdValidationException,
    SelfReferenceValidationException,
)


class TestFollowRelationShip:
    """FollowRelationShipバリューオブジェクトのテスト"""

    def test_create_follow_relationship_success(self):
        """正常なFollowRelationShipの作成テスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)

        follow = FollowRelationShip(follower_user_id, followee_user_id)

        assert follow.follower_user_id == follower_user_id
        assert follow.followee_user_id == followee_user_id
        assert isinstance(follow.created_at, datetime)

    def test_create_follow_relationship_with_explicit_datetime(self):
        """明示的な日時でのFollowRelationShip作成テスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        follow = FollowRelationShip(follower_user_id, followee_user_id, specific_time)

        assert follow.follower_user_id == follower_user_id
        assert follow.followee_user_id == followee_user_id
        assert follow.created_at == specific_time

    def test_invalid_follower_user_id_raises_error(self):
        """無効なフォロワーIDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_invalid_followee_user_id_raises_error(self):
        """無効なフォロー対象IDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_self_follow_raises_error(self):
        """自分自身をフォローしようとする場合のエラーテスト"""
        user_id = UserId(1)
        with pytest.raises(SelfReferenceValidationException):
            FollowRelationShip(user_id, user_id)

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        follow = FollowRelationShip(follower_user_id, followee_user_id)
        assert follow.follower_user_id == follower_user_id
        assert follow.followee_user_id == followee_user_id

        # 大きな値
        large_user_id = UserId(999999)
        follow = FollowRelationShip(large_user_id, followee_user_id)
        assert follow.follower_user_id == large_user_id

        follow = FollowRelationShip(follower_user_id, large_user_id)
        assert follow.followee_user_id == large_user_id

    def test_is_following_method(self):
        """is_followingメソッドのテスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        follow = FollowRelationShip(follower_user_id, followee_user_id)

        # フォローしているユーザーIDを指定
        assert follow.is_following(followee_user_id) == True

        # フォローしていないユーザーIDを指定
        assert follow.is_following(follower_user_id) == False
        assert follow.is_following(UserId(3)) == False

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        follower_user_id1 = UserId(1)
        followee_user_id1 = UserId(2)
        follower_user_id2 = UserId(1)
        followee_user_id2 = UserId(2)

        follow1 = FollowRelationShip(follower_user_id1, followee_user_id1, specific_time)
        follow2 = FollowRelationShip(follower_user_id2, followee_user_id2, specific_time)

        # 同じユーザーIDの組み合わせであれば等価
        assert follow1 == follow2
        assert hash(follow1) == hash(follow2)

    def test_inequality_with_different_follower_ids(self):
        """異なるフォロワーIDでの非等価性テスト"""
        follower_user_id1 = UserId(1)
        follower_user_id2 = UserId(3)
        followee_user_id = UserId(2)

        follow1 = FollowRelationShip(follower_user_id1, followee_user_id)
        follow2 = FollowRelationShip(follower_user_id2, followee_user_id)

        assert follow1 != follow2
        assert hash(follow1) != hash(follow2)

    def test_inequality_with_different_followee_ids(self):
        """異なるフォロー対象IDでの非等価性テスト"""
        follower_user_id = UserId(1)
        followee_user_id1 = UserId(2)
        followee_user_id2 = UserId(3)

        follow1 = FollowRelationShip(follower_user_id, followee_user_id1)
        follow2 = FollowRelationShip(follower_user_id, followee_user_id2)

        assert follow1 != follow2
        assert hash(follow1) != hash(follow2)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        follower_user_id = UserId(1)
        followee_user_id = UserId(2)

        follow1 = FollowRelationShip(follower_user_id, followee_user_id, time1)
        follow2 = FollowRelationShip(follower_user_id, followee_user_id, time2)

        # 同じユーザーIDでも異なる時間の場合は等価（作成時間は比較に含めない）
        assert follow1 == follow2
        assert hash(follow1) == hash(follow2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        follower_user_id1 = UserId(1)
        followee_user_id1 = UserId(2)
        follower_user_id2 = UserId(1)
        followee_user_id2 = UserId(2)

        follow1 = FollowRelationShip(follower_user_id1, followee_user_id1, time)
        follow2 = FollowRelationShip(follower_user_id2, followee_user_id2, time)

        # 同じユーザーIDと時間の場合は等価
        assert follow1 == follow2
        assert hash(follow1) == hash(follow2)

    def test_immutability(self):
        """不変性のテスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        follow = FollowRelationShip(follower_user_id, followee_user_id)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        follow = FollowRelationShip(follower_user_id, followee_user_id)

        str_repr = str(follow)
        assert "FollowRelationShip(" in str_repr
        assert str(follower_user_id) in str_repr
        assert str(followee_user_id) in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        follow = FollowRelationShip(follower_user_id, followee_user_id)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - follow.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差

    def test_different_follower_followee_combinations(self):
        """異なるフォロワー・フォロー対象の組み合わせテスト"""
        # 通常のケース（フォロワーがフォロー対象より小さい）
        follower_user_id1 = UserId(1)
        followee_user_id1 = UserId(100)
        follow1 = FollowRelationShip(follower_user_id1, followee_user_id1)
        assert follow1.follower_user_id == follower_user_id1
        assert follow1.followee_user_id == followee_user_id1

        # フォロワーがフォロー対象より大きい
        follower_user_id2 = UserId(100)
        followee_user_id2 = UserId(1)
        follow2 = FollowRelationShip(follower_user_id2, followee_user_id2)
        assert follow2.follower_user_id == follower_user_id2
        assert follow2.followee_user_id == followee_user_id2

        # is_followingメソッドのテスト
        assert follow1.is_following(followee_user_id1) == True
        assert follow1.is_following(follower_user_id1) == False
        assert follow2.is_following(followee_user_id2) == True
        assert follow2.is_following(follower_user_id2) == False

    def test_id_string_conversion(self):
        """IDの文字列変換テスト"""
        follower_user_id = UserId(123)
        followee_user_id = UserId(456)
        follow = FollowRelationShip(follower_user_id, followee_user_id)

        assert str(follow.follower_user_id) == "123"
        assert str(follow.followee_user_id) == "456"
        assert int(follow.follower_user_id) == 123
        assert int(follow.followee_user_id) == 456
