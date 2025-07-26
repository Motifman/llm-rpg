import pytest
from unittest.mock import Mock, MagicMock
from typing import List

from game.object.chest import Chest
from game.item.item import Item
from game.action.actions.interactable_action import OpenChestStrategy, OpenChestCommand, OpenChestResult
from game.player.player import Player
from game.world.spot import Spot
from game.world.spot_manager import SpotManager
from game.player.player_manager import PlayerManager
from game.core.game_context import GameContext
from game.enums import Role


class TestChest:
    """Chestクラスの基本的な機能テスト"""
    
    def test_chest_creation(self):
        """宝箱の作成テスト"""
        chest = Chest("test_chest", "テスト宝箱")
        assert chest.chest_id == "test_chest"
        assert chest.display_name == "テスト宝箱"
        assert chest.contents == []
        assert chest.is_locked == False
        assert chest.is_opened == False
        assert chest.required_item_id is None
    
    def test_chest_creation_with_contents(self):
        """アイテム付き宝箱の作成テスト"""
        items = [Item("sword", "鉄の剣"), Item("potion", "回復薬")]
        chest = Chest("treasure_chest", "宝物箱", contents=items)
        assert len(chest.contents) == 2
        assert chest.contents[0].item_id == "sword"
        assert chest.contents[1].item_id == "potion"
    
    def test_chest_creation_locked(self):
        """ロックされた宝箱の作成テスト"""
        chest = Chest("locked_chest", "ロック宝箱", is_locked=True, required_item_id="golden_key")
        assert chest.is_locked == True
        assert chest.required_item_id == "golden_key"
    
    def test_chest_str_representation(self):
        """宝箱の文字列表現テスト"""
        chest = Chest("test_chest", "テスト宝箱")
        expected = "Chest(id='test_chest', name='テスト宝箱', contents=[], opened=False, locked=False)"
        assert str(chest) == expected
    
    def test_chest_getters(self):
        """宝箱のgetterメソッドテスト"""
        chest = Chest("test_chest", "テスト宝箱")
        assert chest.get_chest_id() == "test_chest"
        assert chest.get_display_name() == "テスト宝箱"
    
    def test_chest_unlock(self):
        """宝箱のアンロックテスト"""
        chest = Chest("locked_chest", "ロック宝箱", is_locked=True)
        assert chest.is_locked == True
        
        result = chest.unlock()
        assert result == True
        assert chest.is_locked == False
    
    def test_chest_unlock_already_unlocked(self):
        """既にアンロックされた宝箱のアンロックテスト"""
        chest = Chest("unlocked_chest", "アンロック宝箱", is_locked=False)
        result = chest.unlock()
        assert result == False
        assert chest.is_locked == False
    
    def test_chest_open_unlocked_empty(self):
        """空のアンロック宝箱を開けるテスト"""
        chest = Chest("empty_chest", "空の宝箱")
        items = chest.open()
        assert items == []
        assert chest.is_opened == True
    
    def test_chest_open_unlocked_with_contents(self):
        """アイテム付きアンロック宝箱を開けるテスト"""
        items = [Item("sword", "鉄の剣"), Item("potion", "回復薬")]
        chest = Chest("treasure_chest", "宝物箱", contents=items)
        
        opened_items = chest.open()
        assert len(opened_items) == 2
        assert opened_items[0].item_id == "sword"
        assert opened_items[1].item_id == "potion"
        assert chest.is_opened == True
        assert len(chest.contents) == 0  # 中身は空になる
    
    def test_chest_open_locked(self):
        """ロックされた宝箱を開けるテスト"""
        chest = Chest("locked_chest", "ロック宝箱", is_locked=True)
        items = chest.open()
        assert items == []
        assert chest.is_opened == False  # ロックされているので開かない
    
    def test_chest_open_already_opened(self):
        """既に開かれた宝箱を開けるテスト"""
        items = [Item("sword", "鉄の剣")]
        chest = Chest("opened_chest", "開かれた宝箱", contents=items)
        chest.open()  # 一度開く
        
        # 再度開こうとする
        items = chest.open()
        assert items == []
        assert chest.is_opened == True
    
    def test_chest_set_contents(self):
        """宝箱の内容設定テスト"""
        chest = Chest("empty_chest", "空の宝箱")
        new_items = [Item("magic_ring", "魔法の指輪")]
        
        chest.set_contents(new_items)
        assert len(chest.contents) == 1
        assert chest.contents[0].item_id == "magic_ring"
        assert chest.is_opened == False  # リセットされる
    
    def test_chest_get_remaining_contents(self):
        """宝箱の残り内容取得テスト"""
        items = [Item("sword", "鉄の剣"), Item("potion", "回復薬")]
        chest = Chest("treasure_chest", "宝物箱", contents=items)
        
        # 開く前
        remaining = chest.get_remaining_contents()
        assert len(remaining) == 2
        
        # 開いた後
        chest.open()
        remaining = chest.get_remaining_contents()
        assert len(remaining) == 0


class TestOpenChestStrategy:
    """宝箱を開ける戦略クラスのテスト"""
    
    def setup_method(self):
        """テスト前のセットアップ"""
        self.player_manager = PlayerManager()
        self.player = Player("test_player", "テストプレイヤー", Role.CITIZEN)
        self.player_manager.add_player(self.player)
        
        self.spot_manager = SpotManager()
        self.spot = Spot("test_spot", "テストスポット", "テスト用の場所")
        self.spot_manager.add_spot(self.spot)
        
        self.game_context = GameContext(self.player_manager, self.spot_manager)
        self.player.set_current_spot_id("test_spot")
        
        self.strategy = OpenChestStrategy()
    
    def test_open_chest_strategy_creation(self):
        """宝箱を開ける戦略の作成テスト"""
        strategy = OpenChestStrategy()
        assert strategy.get_name() == "宝箱を開ける"
    
    def test_get_required_arguments_no_chests(self):
        """宝箱がない場合の引数取得テスト"""
        arguments = self.strategy.get_required_arguments(self.player, self.game_context)
        assert arguments == []
    
    def test_get_required_arguments_with_chests(self):
        """宝箱がある場合の引数取得テスト"""
        chest1 = Chest("chest_1", "宝箱1")
        chest2 = Chest("chest_2", "宝箱2")
        self.spot.add_interactable(chest1)
        self.spot.add_interactable(chest2)
        
        argument_infos = self.strategy.get_required_arguments(self.player, self.game_context)
        assert len(argument_infos) == 1
        argument_info = argument_infos[0]
        assert argument_info.name == "chest_name"
        assert argument_info.description == "開ける宝箱を選択してください"
        assert "宝箱1" in argument_info.candidates
        assert "宝箱2" in argument_info.candidates
    
    def test_get_required_arguments_with_opened_chest(self):
        """開かれた宝箱がある場合の引数取得テスト"""
        chest = Chest("chest_1", "宝箱1")
        chest.open()  # 宝箱を開く
        self.spot.add_interactable(chest)
        
        argument_infos = self.strategy.get_required_arguments(self.player, self.game_context)
        assert argument_infos == []  # 開かれた宝箱は含まれない
    
    def test_can_execute_no_chests(self):
        """宝箱がない場合の実行可能性テスト"""
        can_execute = self.strategy.can_execute(self.player, self.game_context)
        assert can_execute == False
    
    def test_can_execute_with_chests(self):
        """宝箱がある場合の実行可能性テスト"""
        chest = Chest("chest_1", "宝箱1")
        self.spot.add_interactable(chest)
        
        can_execute = self.strategy.can_execute(self.player, self.game_context)
        assert can_execute == True
    
    def test_can_execute_with_opened_chest(self):
        """開かれた宝箱のみの場合の実行可能性テスト"""
        chest = Chest("chest_1", "宝箱1")
        chest.open()  # 宝箱を開く
        self.spot.add_interactable(chest)
        
        can_execute = self.strategy.can_execute(self.player, self.game_context)
        assert can_execute == False
    
    def test_build_action_command_with_name(self):
        """名前指定でのアクションコマンド作成テスト"""
        command = self.strategy.build_action_command(self.player, self.game_context, chest_name="宝箱1")
        assert isinstance(command, OpenChestCommand)
        assert command.target_chest_name == "宝箱1"
    
    def test_build_action_command_without_name(self):
        """名前指定なしでのアクションコマンド作成テスト"""
        command = self.strategy.build_action_command(self.player, self.game_context)
        assert isinstance(command, OpenChestCommand)
        assert command.target_chest_name is None


class TestOpenChestCommand:
    """宝箱を開けるコマンドのテスト"""
    
    def setup_method(self):
        """テスト前のセットアップ"""
        self.player_manager = PlayerManager()
        self.player = Player("test_player", "テストプレイヤー", Role.CITIZEN)
        self.player_manager.add_player(self.player)
        
        self.spot_manager = SpotManager()
        self.spot = Spot("test_spot", "テストスポット", "テスト用の場所")
        self.spot_manager.add_spot(self.spot)
        
        self.game_context = GameContext(self.player_manager, self.spot_manager)
        self.player.set_current_spot_id("test_spot")
    
    def test_open_chest_command_creation(self):
        """宝箱を開けるコマンドの作成テスト"""
        command = OpenChestCommand("宝箱1")
        assert command.action_name == "宝箱を開ける"
        assert command.target_chest_name == "宝箱1"
    
    def test_execute_no_spot(self):
        """スポットが存在しない場合の実行テスト"""
        self.player.set_current_spot_id("non_existent_spot")
        command = OpenChestCommand()
        
        result = command.execute(self.player, self.game_context)
        assert result.success == False
        assert "現在のスポットが見つかりません" in result.message
    
    def test_execute_no_chests(self):
        """宝箱がない場合の実行テスト"""
        command = OpenChestCommand()
        
        result = command.execute(self.player, self.game_context)
        assert result.success == False
        assert "この場所に開けることができる宝箱はありません" in result.message
    
    def test_execute_chest_not_found(self):
        """指定した名前の宝箱が見つからない場合の実行テスト"""
        chest = Chest("chest_1", "宝箱1")
        self.spot.add_interactable(chest)
        
        command = OpenChestCommand("存在しない宝箱")
        
        result = command.execute(self.player, self.game_context)
        assert result.success == False
        assert "「存在しない宝箱」という名前の宝箱は見つかりません" in result.message
    
    def test_execute_locked_chest_no_key(self):
        """鍵なしでロックされた宝箱を開けるテスト"""
        chest = Chest("locked_chest", "ロック宝箱", is_locked=True, required_item_id="golden_key")
        self.spot.add_interactable(chest)
        
        command = OpenChestCommand("ロック宝箱")
        
        result = command.execute(self.player, self.game_context)
        assert result.success == False
        assert "「golden_key」が必要です" in result.message
    
    def test_execute_locked_chest_with_key(self):
        """鍵ありでロックされた宝箱を開けるテスト"""
        chest = Chest("locked_chest", "ロック宝箱", is_locked=True, required_item_id="golden_key")
        self.spot.add_interactable(chest)
        
        # 鍵をプレイヤーに追加
        key = Item("golden_key", "黄金の鍵")
        self.player.add_item(key)
        
        command = OpenChestCommand("ロック宝箱")
        
        result = command.execute(self.player, self.game_context)
        assert result.success == True
        assert chest.is_locked == False
        assert not self.player.has_item("golden_key")  # 鍵は消費される
    
    def test_execute_unlocked_chest_with_contents(self):
        """アンロックされた宝箱を開けるテスト（アイテムあり）"""
        items = [Item("sword", "鉄の剣"), Item("potion", "回復薬")]
        chest = Chest("treasure_chest", "宝物箱", contents=items)
        self.spot.add_interactable(chest)
        
        command = OpenChestCommand("宝物箱")
        
        result = command.execute(self.player, self.game_context)
        assert result.success == True
        assert chest.is_opened == True
        assert len(chest.contents) == 0
        
        # プレイヤーにアイテムが追加されているかチェック
        inventory_items = self.player.get_inventory().get_items()
        assert len(inventory_items) == 2
        item_ids = [item.item_id for item in inventory_items]
        assert "sword" in item_ids
        assert "potion" in item_ids
    
    def test_execute_unlocked_empty_chest(self):
        """アンロックされた空の宝箱を開けるテスト"""
        chest = Chest("empty_chest", "空の宝箱")
        self.spot.add_interactable(chest)
        
        command = OpenChestCommand("空の宝箱")
        
        result = command.execute(self.player, self.game_context)
        assert result.success == True
        assert chest.is_opened == True
        assert "中は空でした" in result.message
    
    def test_execute_first_chest_no_name(self):
        """名前指定なしで最初の宝箱を開けるテスト"""
        chest1 = Chest("chest_1", "宝箱1", contents=[Item("sword", "鉄の剣")])
        chest2 = Chest("chest_2", "宝箱2", contents=[Item("potion", "回復薬")])
        self.spot.add_interactable(chest1)
        self.spot.add_interactable(chest2)
        
        command = OpenChestCommand()  # 名前指定なし
        
        result = command.execute(self.player, self.game_context)
        assert result.success == True
        assert chest1.is_opened == True  # 最初の宝箱が開かれる
        assert chest2.is_opened == False  # 2番目の宝箱は開かれない


class TestOpenChestResult:
    """宝箱を開ける結果クラスのテスト"""
    
    def test_open_chest_result_creation_success(self):
        """成功時の結果作成テスト"""
        items_details = ["sword - 鉄の剣", "potion - 回復薬"]
        result = OpenChestResult(True, "宝箱を開けました", items_details)
        
        assert result.success == True
        assert result.message == "宝箱を開けました"
        assert result.items_details == items_details
    
    def test_open_chest_result_creation_failure(self):
        """失敗時の結果作成テスト"""
        result = OpenChestResult(False, "鍵が必要です")
        
        assert result.success == False
        assert result.message == "鍵が必要です"
        assert result.items_details is None
    
    def test_to_feedback_message_success(self):
        """成功時のフィードバックメッセージテスト"""
        items_details = ["sword - 鉄の剣", "potion - 回復薬"]
        result = OpenChestResult(True, "宝箱を開けました", items_details)
        
        message = result.to_feedback_message("プレイヤー1")
        assert "プレイヤー1 は宝箱を開けてアイテムを入手しました" in message
        assert "sword - 鉄の剣" in message
        assert "potion - 回復薬" in message
    
    def test_to_feedback_message_failure(self):
        """失敗時のフィードバックメッセージテスト"""
        result = OpenChestResult(False, "鍵が必要です")
        
        message = result.to_feedback_message("プレイヤー1")
        assert "プレイヤー1 は宝箱を開けることに失敗しました" in message
        assert "鍵が必要です" in message
    
    def test_to_feedback_message_no_items(self):
        """アイテムなしのフィードバックメッセージテスト"""
        result = OpenChestResult(True, "宝箱を開けました", [])
        
        message = result.to_feedback_message("プレイヤー1")
        assert "プレイヤー1 は宝箱を開けてアイテムを入手しました" in message
        assert "なし" in message


class TestChestIntegration:
    """宝箱システムの統合テスト"""
    
    def setup_method(self):
        """テスト前のセットアップ"""
        self.player_manager = PlayerManager()
        self.player = Player("test_player", "テストプレイヤー", Role.CITIZEN)
        self.player_manager.add_player(self.player)
        
        self.spot_manager = SpotManager()
        self.spot = Spot("treasure_room", "宝物部屋", "宝箱がある部屋")
        self.spot_manager.add_spot(self.spot)
        
        self.game_context = GameContext(self.player_manager, self.spot_manager)
        self.player.set_current_spot_id("treasure_room")
    
    def test_multiple_chests_scenario(self):
        """複数宝箱のシナリオテスト"""
        # 複数の宝箱を作成
        chest1 = Chest("chest_1", "古い宝箱", contents=[Item("sword", "鉄の剣")])
        chest2 = Chest("chest_2", "銀の宝箱", contents=[Item("magic_ring", "魔法の指輪")], 
                      is_locked=True, required_item_id="silver_key")
        chest3 = Chest("chest_3", "黄金の宝箱", contents=[Item("gold_coin", "金貨")], 
                      is_locked=True, required_item_id="golden_key")
        
        self.spot.add_interactable(chest1)
        self.spot.add_interactable(chest2)
        self.spot.add_interactable(chest3)
        
        # 1. 最初の宝箱を開ける
        command = OpenChestCommand("古い宝箱")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == True
        assert chest1.is_opened == True
        assert self.player.has_item("sword")
        
        # 2. 鍵なしで銀の宝箱を開けようとする
        command = OpenChestCommand("銀の宝箱")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == False
        assert "silver_key" in result.message
        
        # 3. 銀の鍵を入手して銀の宝箱を開ける
        silver_key = Item("silver_key", "銀の鍵")
        self.player.add_item(silver_key)
        
        command = OpenChestCommand("銀の宝箱")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == True
        assert chest2.is_opened == True
        assert self.player.has_item("magic_ring")
        assert not self.player.has_item("silver_key")  # 鍵は消費される
        
        # 4. 存在しない宝箱を開けようとする
        command = OpenChestCommand("存在しない宝箱")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == False
        assert "存在しない宝箱" in result.message
    
    def test_chest_reopening_attempt(self):
        """既に開かれた宝箱を再度開こうとするテスト"""
        chest = Chest("test_chest", "テスト宝箱", contents=[Item("sword", "鉄の剣")])
        self.spot.add_interactable(chest)
        
        # 1回目：宝箱を開ける
        command = OpenChestCommand("テスト宝箱")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == True
        assert chest.is_opened == True
        
        # 2回目：同じ宝箱を再度開けようとする
        result = command.execute(self.player, self.game_context)
        
        assert result.success == False
        assert "この場所に開けることができる宝箱はありません" in result.message 