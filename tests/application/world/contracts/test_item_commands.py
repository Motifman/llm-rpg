"""旧タイルの入口を撤去しても、残る共有コマンドの入力検証を保証する。"""

import pytest

from ai_rpg_world.application.world.contracts.commands import (
    StoreItemInChestCommand,
    TakeItemFromChestCommand,
    UseItemCommand,
)


def test_store_item_in_chest_command_validation() -> None:
    """収納コマンドの5種類のIDのいずれかが0なら、ValueErrorを投げる。"""
    with pytest.raises(ValueError):
        StoreItemInChestCommand(
            player_id=0, spot_id=1, actor_world_object_id=1, chest_world_object_id=2, item_instance_id=100
        )
    with pytest.raises(ValueError):
        StoreItemInChestCommand(
            player_id=1, spot_id=0, actor_world_object_id=1, chest_world_object_id=2, item_instance_id=100
        )
    with pytest.raises(ValueError):
        StoreItemInChestCommand(
            player_id=1, spot_id=1, actor_world_object_id=0, chest_world_object_id=2, item_instance_id=100
        )
    with pytest.raises(ValueError):
        StoreItemInChestCommand(
            player_id=1, spot_id=1, actor_world_object_id=1, chest_world_object_id=0, item_instance_id=100
        )
    with pytest.raises(ValueError):
        StoreItemInChestCommand(
            player_id=1, spot_id=1, actor_world_object_id=1, chest_world_object_id=2, item_instance_id=0
        )


def test_take_item_from_chest_command_validation() -> None:
    """取得コマンドの5種類のIDのいずれかが0なら、ValueErrorを投げる。"""
    with pytest.raises(ValueError):
        TakeItemFromChestCommand(
            player_id=0, spot_id=1, actor_world_object_id=1, chest_world_object_id=2, item_instance_id=50
        )
    with pytest.raises(ValueError):
        TakeItemFromChestCommand(
            player_id=1, spot_id=0, actor_world_object_id=1, chest_world_object_id=2, item_instance_id=50
        )
    with pytest.raises(ValueError):
        TakeItemFromChestCommand(
            player_id=1, spot_id=1, actor_world_object_id=0, chest_world_object_id=2, item_instance_id=50
        )
    with pytest.raises(ValueError):
        TakeItemFromChestCommand(
            player_id=1, spot_id=1, actor_world_object_id=1, chest_world_object_id=0, item_instance_id=50
        )
    with pytest.raises(ValueError):
        TakeItemFromChestCommand(
            player_id=1, spot_id=1, actor_world_object_id=1, chest_world_object_id=2, item_instance_id=0
        )


def test_use_item_command_validation_player_id_zero_raises() -> None:
    """使用コマンドのplayer_idが0なら、ValueErrorを投げる。"""
    with pytest.raises(ValueError, match="player_id"):
        UseItemCommand(player_id=0, inventory_slot_id=0)


def test_use_item_command_validation_slot_negative_raises() -> None:
    """使用コマンドのinventory_slot_idが負なら、ValueErrorを投げる。"""
    with pytest.raises(ValueError, match="inventory_slot_id"):
        UseItemCommand(player_id=1, inventory_slot_id=-1)
