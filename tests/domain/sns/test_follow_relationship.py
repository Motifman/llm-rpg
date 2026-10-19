from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.exception import (
    SelfReferenceValidationException,
)
from ai_rpg_world.domain.sns.value_object import FollowRelationShip, UserId


class TestFollowRelationShip:
    """FollowRelationShipバリューオブジェクトのテスト"""

    @pytest.mark.parametrize(
        ("actor", "target", "actor_text", "target_text"),
        [(1, 2, "1", "2"), (999999, 2, "999999", "2"),
         (1, 999999, "1", "999999"), (123, 456, "123", "456")],
    )
    def test_create_follow_relationship_success(self, actor, target, actor_text, target_text):
        """最小・大きなIDを各側に保持し、123/456の数値と文字列も取り違えない。"""
        relation = FollowRelationShip(UserId(actor), UserId(target))
        assert relation.follower_user_id == UserId(actor)
        assert relation.followee_user_id == UserId(target)
        assert isinstance(relation.follower_user_id, UserId)
        assert isinstance(relation.followee_user_id, UserId)
        assert isinstance(relation.created_at, datetime)
        assert str(relation.follower_user_id) == actor_text
        assert str(relation.followee_user_id) == target_text
        assert int(relation.follower_user_id) == actor
        assert int(relation.followee_user_id) == target

    def test_create_follow_relationship_with_explicit_datetime(self):
        """明示的な日時でのFollowRelationShip作成テスト"""
        follower_user_id = UserId(1)
        followee_user_id = UserId(2)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        follow = FollowRelationShip(follower_user_id, followee_user_id, specific_time)

        assert follow.follower_user_id == follower_user_id
        assert follow.followee_user_id == followee_user_id
        assert follow.created_at == specific_time

    def test_self_follow_raises_error(self):
        """自分自身をフォローしようとする場合のエラーテスト"""
        user_id = UserId(1)
        with pytest.raises(SelfReferenceValidationException):
            FollowRelationShip(user_id, user_id)

    @pytest.mark.parametrize(("actor", "target"), [(1, 2), (1, 100), (100, 1)])
    def test_is_following_method(self, actor, target):
        """IDの大小に関係なく両側を保持し、対象だけに真を返す。"""
        relation = FollowRelationShip(UserId(actor), UserId(target))
        assert relation.follower_user_id == UserId(actor)
        assert relation.followee_user_id == UserId(target)
        assert relation.is_following(UserId(target)) == True
        assert relation.is_following(UserId(actor)) == False
        assert relation.is_following(UserId(3)) == False

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
        """同じ時刻でも片側IDが異なる関係は非等価で、集合に両方を保持できる。"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        left = FollowRelationShip(UserId(1), UserId(2), time)
        right = FollowRelationShip(UserId(3), UserId(2), time)
        assert left != right
        assert len({left, right}) == 2

    def test_inequality_with_different_followee_ids(self):
        """同じ時刻でも片側IDが異なる関係は非等価で、集合に両方を保持できる。"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        left = FollowRelationShip(UserId(1), UserId(2), time)
        right = FollowRelationShip(UserId(1), UserId(3), time)
        assert left != right
        assert len({left, right}) == 2

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

    @pytest.mark.parametrize("attribute", ["follower_user_id", "followee_user_id", "created_at"])
    def test_immutability(self, attribute):
        """両IDと作成時刻への通常の再代入を拒否し、元の全値を保持する。"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        relation = FollowRelationShip(UserId(1), UserId(2), time)
        replacement = datetime(2024, 1, 1) if attribute == "created_at" else UserId(3)
        with pytest.raises(AttributeError):
            setattr(relation, attribute, replacement)
        assert relation.follower_user_id == UserId(1)
        assert relation.followee_user_id == UserId(2)
        assert relation.created_at == time

    def test_created_at_auto_generation(self):
        """時刻を省略すると、各構築の直前から直後の間の時刻を生成する。"""
        for _ in range(2):
            before = datetime.now()
            relation = FollowRelationShip(UserId(1), UserId(2))
            after = datetime.now()
            assert before <= relation.created_at <= after
