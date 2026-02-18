"""
チェストコマンド関連例外のテスト
"""

import pytest
from ai_rpg_world.application.world.exceptions.command.chest_command_exception import (
    ChestCommandException,
    ChestNotFoundException,
    ItemNotInPlayerInventoryException,
    PlayerInventoryNotFoundException,
    ItemNotInChestCommandException,
)


class TestChestCommandException:
    """ChestCommandException のテスト"""

    def test_create_basic_command_exception(self):
        """基本的なコマンド例外の作成"""
        exception = ChestCommandException("コマンドエラー")

        assert str(exception) == "コマンドエラー"
        assert exception.message == "コマンドエラー"
        assert exception.context == {}

    def test_create_command_exception_with_error_code(self):
        """error_code 付きのコマンド例外作成"""
        exception = ChestCommandException("コマンドエラー", error_code="CHEST_ERROR")

        assert exception.error_code == "CHEST_ERROR"

    def test_create_command_exception_with_context(self):
        """コンテキスト付きのコマンド例外作成"""
        exception = ChestCommandException(
            "コマンドエラー",
            player_id=1,
            spot_id=2,
            chest_id=3,
            item_instance_id=100,
        )

        assert exception.context["player_id"] == 1
        assert exception.context["spot_id"] == 2
        assert exception.context["chest_id"] == 3
        assert exception.context["item_instance_id"] == 100


class TestChestNotFoundException:
    """ChestNotFoundException のテスト"""

    def test_create_chest_not_found_exception(self):
        """チェスト未検出例外の作成"""
        exception = ChestNotFoundException(spot_id=1, chest_id=99)

        assert "スポット 1 のマップまたはチェスト 99 が見つかりません" in str(exception)
        assert exception.error_code == "CHEST_NOT_FOUND"
        assert exception.context["spot_id"] == 1
        assert exception.context["chest_id"] == 99

    def test_chest_not_found_inheritance(self):
        """ChestNotFoundException の継承関係"""
        exception = ChestNotFoundException(1, 2)
        assert isinstance(exception, ChestCommandException)
        assert isinstance(exception, Exception)


class TestItemNotInPlayerInventoryException:
    """ItemNotInPlayerInventoryException のテスト"""

    def test_create_item_not_in_inventory_exception(self):
        """プレイヤーがアイテムを所持していない例外の作成"""
        exception = ItemNotInPlayerInventoryException(player_id=1, item_instance_id=100)

        assert "プレイヤー 1 はアイテム 100 を所持していません" in str(exception)
        assert exception.error_code == "ITEM_NOT_IN_INVENTORY"
        assert exception.context["player_id"] == 1
        assert exception.context["item_instance_id"] == 100

    def test_item_not_in_inventory_inheritance(self):
        """ItemNotInPlayerInventoryException の継承関係"""
        exception = ItemNotInPlayerInventoryException(1, 100)
        assert isinstance(exception, ChestCommandException)
        assert isinstance(exception, Exception)


class TestPlayerInventoryNotFoundException:
    """PlayerInventoryNotFoundException のテスト"""

    def test_create_inventory_not_found_exception(self):
        """プレイヤーインベントリ未検出例外の作成"""
        exception = PlayerInventoryNotFoundException(player_id=1)

        assert "プレイヤー 1 のインベントリが見つかりません" in str(exception)
        assert exception.error_code == "INVENTORY_NOT_FOUND"
        assert exception.context["player_id"] == 1

    def test_inventory_not_found_inheritance(self):
        """PlayerInventoryNotFoundException の継承関係"""
        exception = PlayerInventoryNotFoundException(1)
        assert isinstance(exception, ChestCommandException)
        assert isinstance(exception, Exception)


class TestItemNotInChestCommandException:
    """ItemNotInChestCommandException のテスト"""

    def test_create_item_not_in_chest_exception(self):
        """チェストにアイテムが存在しない例外の作成"""
        exception = ItemNotInChestCommandException(
            spot_id=1, chest_id=2, item_instance_id=50
        )

        assert "スポット 1 のチェスト 2 にアイテム 50 は存在しません" in str(exception)
        assert exception.error_code == "ITEM_NOT_IN_CHEST"
        assert exception.context["spot_id"] == 1
        assert exception.context["chest_id"] == 2
        assert exception.context["item_instance_id"] == 50

    def test_item_not_in_chest_inheritance(self):
        """ItemNotInChestCommandException の継承関係"""
        exception = ItemNotInChestCommandException(1, 2, 50)
        assert isinstance(exception, ChestCommandException)
        assert isinstance(exception, Exception)
