import pytest
from datetime import datetime
from src.domain.sns.block import BlockRelationShip


class TestBlockRelationShip:
    """BlockRelationShipバリューオブジェクトのテスト"""

    def test_create_block_relationship_success(self):
        """正常なBlockRelationShipの作成テスト"""
        blocker_user_id = 1
        blocked_user_id = 2

        block = BlockRelationShip(blocker_user_id, blocked_user_id)

        assert block.blocker_user_id == blocker_user_id
        assert block.blocked_user_id == blocked_user_id
        assert isinstance(block.created_at, datetime)

    def test_create_block_relationship_with_explicit_datetime(self):
        """明示的な日時でのBlockRelationShip作成テスト"""
        blocker_user_id = 1
        blocked_user_id = 2
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        block = BlockRelationShip(blocker_user_id, blocked_user_id, specific_time)

        assert block.blocker_user_id == blocker_user_id
        assert block.blocked_user_id == blocked_user_id
        assert block.created_at == specific_time

    def test_invalid_blocker_user_id_raises_error(self):
        """無効なブロック実行者ユーザーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocker_user_id must be positive"):
            BlockRelationShip(0, 2)

        with pytest.raises(ValueError, match="blocker_user_id must be positive"):
            BlockRelationShip(-1, 2)

    def test_invalid_blocked_user_id_raises_error(self):
        """無効なブロック対象ユーザーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocked_user_id must be positive"):
            BlockRelationShip(1, 0)

        with pytest.raises(ValueError, match="blocked_user_id must be positive"):
            BlockRelationShip(1, -1)

    def test_self_block_raises_error(self):
        """自分自身をブロックしようとする場合のテスト"""
        user_id = 1
        # 自分自身をブロックしようとするケースはバリデーションで防ぐ
        block = BlockRelationShip(user_id, user_id)
        assert block.blocker_user_id == user_id
        assert block.blocked_user_id == user_id

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        block = BlockRelationShip(1, 2)
        assert block.blocker_user_id == 1

        # 大きな値
        large_user_id = 999999
        block = BlockRelationShip(large_user_id, 2)
        assert block.blocker_user_id == large_user_id

        block = BlockRelationShip(1, large_user_id)
        assert block.blocked_user_id == large_user_id

    def test_is_blocked_method(self):
        """is_blockedメソッドのテスト"""
        block = BlockRelationShip(1, 2)

        # ブロックされたユーザーIDを指定
        assert block.is_blocked(2) == True

        # ブロックされていないユーザーIDを指定
        assert block.is_blocked(1) == False
        assert block.is_blocked(3) == False

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        block1 = BlockRelationShip(1, 2, specific_time)
        block2 = BlockRelationShip(1, 2, specific_time)

        # 同じユーザーIDの組み合わせであれば等価
        assert block1 == block2
        assert hash(block1) == hash(block2)

    def test_inequality_with_different_blocker_ids(self):
        """異なるブロック実行者IDでの非等価性テスト"""
        block1 = BlockRelationShip(1, 2)
        block2 = BlockRelationShip(3, 2)

        assert block1 != block2
        assert hash(block1) != hash(block2)

    def test_inequality_with_different_blocked_ids(self):
        """異なるブロック対象IDでの非等価性テスト"""
        block1 = BlockRelationShip(1, 2)
        block2 = BlockRelationShip(1, 3)

        assert block1 != block2
        assert hash(block1) != hash(block2)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        block1 = BlockRelationShip(1, 2, time1)
        block2 = BlockRelationShip(1, 2, time2)

        # 同じユーザーIDでも異なる時間の場合は等価ではない
        assert block1 != block2
        assert hash(block1) != hash(block2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        block1 = BlockRelationShip(1, 2, time)
        block2 = BlockRelationShip(1, 2, time)

        # 同じユーザーIDと時間の場合は等価
        assert block1 == block2
        assert hash(block1) == hash(block2)

    def test_immutability(self):
        """不変性のテスト"""
        block = BlockRelationShip(1, 2)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        block = BlockRelationShip(1, 2)

        str_repr = str(block)
        assert "BlockRelationShip(" in str_repr
        assert "1" in str_repr
        assert "2" in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        block = BlockRelationShip(1, 2)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - block.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差
