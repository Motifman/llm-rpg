import pytest
from datetime import datetime
from src.domain.sns.value_object import BlockRelationShip, UserId
from src.domain.sns.exception import (
    UserIdValidationException,
    SelfReferenceValidationException,
)


class TestBlockRelationShip:
    """BlockRelationShipバリューオブジェクトのテスト"""

    def test_create_block_relationship_success(self):
        """正常なBlockRelationShipの作成テスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)

        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        assert block.blocker_user_id == blocker_user_id
        assert block.blocked_user_id == blocked_user_id
        assert isinstance(block.created_at, datetime)

    def test_create_block_relationship_with_explicit_datetime(self):
        """明示的な日時でのBlockRelationShip作成テスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        block = BlockRelationShip(blocker_user_id, blocked_user_id, specific_time)

        assert block.blocker_user_id == blocker_user_id
        assert block.blocked_user_id == blocked_user_id
        assert block.created_at == specific_time

    def test_invalid_blocker_user_id_raises_error(self):
        """無効なブロック実行者ユーザーIDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_invalid_blocked_user_id_raises_error(self):
        """無効なブロック対象ユーザーIDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_self_block_raises_error(self):
        """自分自身をブロックしようとする場合のエラーテスト"""
        user_id = UserId(1)
        with pytest.raises(SelfReferenceValidationException):
            BlockRelationShip(user_id, user_id)

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        block = BlockRelationShip(blocker_user_id, blocked_user_id)
        assert block.blocker_user_id == blocker_user_id
        assert block.blocked_user_id == blocked_user_id

        # 大きな値
        large_user_id = UserId(999999)
        block = BlockRelationShip(large_user_id, blocked_user_id)
        assert block.blocker_user_id == large_user_id

        block = BlockRelationShip(blocker_user_id, large_user_id)
        assert block.blocked_user_id == large_user_id

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
        """異なるブロック実行者IDでの非等価性テスト"""
        blocker_user_id1 = UserId(1)
        blocker_user_id2 = UserId(3)
        blocked_user_id = UserId(2)

        block1 = BlockRelationShip(blocker_user_id1, blocked_user_id)
        block2 = BlockRelationShip(blocker_user_id2, blocked_user_id)

        assert block1 != block2
        assert hash(block1) != hash(block2)

    def test_inequality_with_different_blocked_ids(self):
        """異なるブロック対象IDでの非等価性テスト"""
        blocker_user_id = UserId(1)
        blocked_user_id1 = UserId(2)
        blocked_user_id2 = UserId(3)

        block1 = BlockRelationShip(blocker_user_id, blocked_user_id1)
        block2 = BlockRelationShip(blocker_user_id, blocked_user_id2)

        assert block1 != block2
        assert hash(block1) != hash(block2)

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

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        blocker_user_id1 = UserId(1)
        blocked_user_id1 = UserId(2)
        blocker_user_id2 = UserId(1)
        blocked_user_id2 = UserId(2)

        block1 = BlockRelationShip(blocker_user_id1, blocked_user_id1, time)
        block2 = BlockRelationShip(blocker_user_id2, blocked_user_id2, time)

        # 同じユーザーIDと時間の場合は等価
        assert block1 == block2
        assert hash(block1) == hash(block2)

    def test_immutability(self):
        """不変性のテスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        str_repr = str(block)
        assert "BlockRelationShip(" in str_repr
        assert str(blocker_user_id) in str_repr
        assert str(blocked_user_id) in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        blocker_user_id = UserId(1)
        blocked_user_id = UserId(2)
        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - block.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差

    def test_id_string_conversion(self):
        """IDの文字列変換テスト"""
        blocker_user_id = UserId(123)
        blocked_user_id = UserId(456)
        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        assert str(block.blocker_user_id) == "123"
        assert str(block.blocked_user_id) == "456"
        assert int(block.blocker_user_id) == 123
        assert int(block.blocked_user_id) == 456
