"""目的地設定の命令が、残る共通契約の入力規則を守ることを保証する。"""

import pytest

from ai_rpg_world.application.world.contracts.commands import CancelMovementCommand, SetDestinationCommand


class TestSetDestinationCommandValidation:
    """SetDestinationCommand が目的地の種類に応じて必要なIDを検証する。"""

    def test_destination_type_location_requires_positive_target_location_area_id(self):
        """destination_type が location のとき target_location_area_id が正の整数であること"""
        with pytest.raises(ValueError, match="target_location_area_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="location",
                target_spot_id=1,
                target_location_area_id=None,
            )
        with pytest.raises(ValueError, match="target_location_area_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="location",
                target_spot_id=1,
                target_location_area_id=0,
            )

    def test_destination_type_spot_does_not_require_target_location_area_id(self):
        """destination_type が spot のとき target_location_area_id は不要"""
        cmd = SetDestinationCommand(player_id=1, destination_type="spot", target_spot_id=2)
        assert cmd.destination_type == "spot"
        assert cmd.target_spot_id == 2
        assert cmd.target_location_area_id is None

    def test_destination_type_location_with_valid_target_location_area_id(self):
        """destination_type が location のとき target_location_area_id を指定できる"""
        cmd = SetDestinationCommand(
            player_id=1,
            destination_type="location",
            target_spot_id=1,
            target_location_area_id=10,
        )
        assert cmd.target_location_area_id == 10

    def test_destination_type_object_requires_positive_target_world_object_id(self):
        """destination_type が object のとき target_world_object_id が正の整数であること"""
        with pytest.raises(ValueError, match="target_world_object_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="object",
                target_spot_id=1,
                target_world_object_id=None,
            )
        with pytest.raises(ValueError, match="target_world_object_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="object",
                target_spot_id=1,
                target_world_object_id=0,
            )

    def test_destination_type_object_with_valid_target_world_object_id(self):
        """destination_type が object のとき target_world_object_id を指定できる"""
        cmd = SetDestinationCommand(
            player_id=1,
            destination_type="object",
            target_spot_id=1,
            target_world_object_id=200,
        )
        assert cmd.target_world_object_id == 200


class TestCancelMovementCommandValidation:
    """CancelMovementCommand は無効なプレイヤーIDを拒否する。"""

    def test_cancel_movement_command_player_id_invalid_raises(self):
        """CancelMovementCommand の player_id が 0 以下の場合 ValueError"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            CancelMovementCommand(player_id=0)
