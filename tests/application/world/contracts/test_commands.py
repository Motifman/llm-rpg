"""DropItemCommand の境界値・バリデーションテスト"""

import pytest
from ai_rpg_world.application.world.contracts.commands import DropItemCommand


class TestDropItemCommand:
    """DropItemCommand のテスト"""

    class TestCreateSuccess:
        """正常作成のテスト"""

        def test_create_with_valid_positive_player_id_and_zero_slot(self):
            """player_id=1, inventory_slot_id=0 で作成できること"""
            cmd = DropItemCommand(player_id=1, inventory_slot_id=0)
            assert cmd.player_id == 1
            assert cmd.inventory_slot_id == 0

        def test_create_with_valid_large_values(self):
            """大きな正の値で作成できること"""
            cmd = DropItemCommand(player_id=999999, inventory_slot_id=99)
            assert cmd.player_id == 999999
            assert cmd.inventory_slot_id == 99

        def test_create_with_inventory_slot_id_zero(self):
            """inventory_slot_id=0 は有効（境界値）"""
            cmd = DropItemCommand(player_id=1, inventory_slot_id=0)
            assert cmd.inventory_slot_id == 0

    class TestPlayerIdValidation:
        """player_id バリデーションのテスト"""

        def test_player_id_zero_raises_value_error(self):
            """player_id=0 のとき ValueError"""
            with pytest.raises(ValueError, match="player_id must be greater than 0"):
                DropItemCommand(player_id=0, inventory_slot_id=0)

        def test_player_id_negative_raises_value_error(self):
            """player_id が負のとき ValueError"""
            with pytest.raises(ValueError, match="player_id must be greater than 0"):
                DropItemCommand(player_id=-1, inventory_slot_id=0)

            with pytest.raises(ValueError, match="player_id must be greater than 0"):
                DropItemCommand(player_id=-100, inventory_slot_id=0)

    class TestInventorySlotIdValidation:
        """inventory_slot_id バリデーションのテスト"""

        def test_inventory_slot_id_negative_raises_value_error(self):
            """inventory_slot_id が負のとき ValueError"""
            with pytest.raises(ValueError, match="inventory_slot_id must be non-negative"):
                DropItemCommand(player_id=1, inventory_slot_id=-1)

            with pytest.raises(ValueError, match="inventory_slot_id must be non-negative"):
                DropItemCommand(player_id=1, inventory_slot_id=-99)

    class TestImmutability:
        """不変性のテスト"""

        def test_command_is_frozen(self):
            """コマンドは frozen で属性変更不可"""
            cmd = DropItemCommand(player_id=1, inventory_slot_id=0)
            with pytest.raises(AttributeError):
                cmd.player_id = 2
            with pytest.raises(AttributeError):
                cmd.inventory_slot_id = 1
