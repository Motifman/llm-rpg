from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.exception import (
    SelfReferenceValidationException,
)
from ai_rpg_world.domain.sns.value_object import BlockRelationShip, UserId


class TestBlockRelationShip:
    """BlockRelationShipバリューオブジェクトのテスト"""

    @pytest.mark.parametrize(
        ("actor", "target", "actor_text", "target_text"),
        [(1, 2, "1", "2"), (999999, 2, "999999", "2"),
         (1, 999999, "1", "999999"), (123, 456, "123", "456")],
    )
    def test_create_block_relationship_success(self, actor, target, actor_text, target_text):
        """最小・大きなIDを各側に保持し、123/456の数値と文字列も取り違えない。"""
        relation = BlockRelationShip(UserId(actor), UserId(target))
        assert relation.blocker_user_id == UserId(actor)
        assert relation.blocked_user_id == UserId(target)
        assert isinstance(relation.blocker_user_id, UserId)
        assert isinstance(relation.blocked_user_id, UserId)
        assert isinstance(relation.created_at, datetime)
        assert str(relation.blocker_user_id) == actor_text
        assert str(relation.blocked_user_id) == target_text
        assert int(relation.blocker_user_id) == actor
        assert int(relation.blocked_user_id) == target

    def test_create_block_relationship_with_explicit_datetime(self):
        """明示的な日時でのBlockRelationShip作成テスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        block = BlockRelationShip(blocker_user_id, blocked_user_id, specific_time)

        assert block.blocker_user_id == blocker_user_id
        assert block.blocked_user_id == blocked_user_id
        assert block.created_at == specific_time

    def test_self_block_raises_error(self):
        """自分自身をブロックしようとする場合のエラーテスト"""
        user_id = UserId(1)
        with pytest.raises(SelfReferenceValidationException):
            BlockRelationShip(user_id, user_id)

    def test_is_blocked_method(self):
        """is_blockedメソッドのテスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        # ブロックされたユーザーIDを指定
        assert block.is_blocked(blocked_user_id) == True

        # ブロックされていないユーザーIDを指定
        assert block.is_blocked(blocker_user_id) == False
        assert block.is_blocked(UserId(3)) == False

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        blocker_user_id1 = UserId(1)
        blocked_user_id1 = UserId(2)
        blocker_user_id2 = UserId(1)
        blocked_user_id2 = UserId(2)

        block1 = BlockRelationShip(blocker_user_id1, blocked_user_id1, specific_time)
        block2 = BlockRelationShip(blocker_user_id2, blocked_user_id2, specific_time)

        # 同じユーザーIDの組み合わせであれば等価
        assert block1 == block2
        assert hash(block1) == hash(block2)

    def test_inequality_with_different_blocker_ids(self):
        """同じ時刻でも片側IDが異なる関係は非等価で、集合に両方を保持できる。"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        left = BlockRelationShip(UserId(1), UserId(2), time)
        right = BlockRelationShip(UserId(3), UserId(2), time)
        assert left != right
        assert len({left, right}) == 2

    def test_inequality_with_different_blocked_ids(self):
        """同じ時刻でも片側IDが異なる関係は非等価で、集合に両方を保持できる。"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        left = BlockRelationShip(UserId(1), UserId(2), time)
        right = BlockRelationShip(UserId(1), UserId(3), time)
        assert left != right
        assert len({left, right}) == 2

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)

        block1 = BlockRelationShip(blocker_user_id, blocked_user_id, time1)
        block2 = BlockRelationShip(blocker_user_id, blocked_user_id, time2)

        # 同じユーザーIDでも異なる時間の場合は等価（作成時間は比較に含めない）
        assert block1 == block2
        assert hash(block1) == hash(block2)

    @pytest.mark.parametrize("attribute", ["blocker_user_id", "blocked_user_id", "created_at"])
    def test_immutability(self, attribute):
        """両IDと作成時刻への通常の再代入を拒否し、元の全値を保持する。"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        relation = BlockRelationShip(UserId(1), UserId(2), time)
        replacement = datetime(2024, 1, 1) if attribute == "created_at" else UserId(3)
        with pytest.raises(AttributeError):
            setattr(relation, attribute, replacement)
        assert relation.blocker_user_id == UserId(1)
        assert relation.blocked_user_id == UserId(2)
        assert relation.created_at == time

    def test_created_at_auto_generation(self):
        """時刻を省略すると、各構築の直前から直後の間の時刻を生成する。"""
        for _ in range(2):
            before = datetime.now()
            relation = BlockRelationShip(UserId(1), UserId(2))
            after = datetime.now()
            assert before <= relation.created_at <= after
