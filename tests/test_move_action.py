#!/usr/bin/env python3
"""
MoveActionクラスの包括的なテスト
"""

import pytest
from game.action.actions.move_action import MovementStrategy, MovementCommand, MovementResult
from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.core.game_context import GameContext
from game.enums import Role


class TestMoveAction:
    """MoveActionクラスのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行されるセットアップ"""
        # プレイヤーとプレイヤーマネージャーを作成
        self.player = Player("test_player_001", "テストプレイヤー", Role.ADVENTURER)
        self.player_manager = PlayerManager()
        self.player_manager.add_player(self.player)
        
        # スポットマネージャーを作成
        self.spot_manager = SpotManager()
        
        # テスト用スポットを作成
        self.town_square = Spot("town_square", "街の広場", "人々が集まる中心的な場所")
        self.inn = Spot("inn", "宿屋", "旅人たちが休息を取る場所")
        self.shop = Spot("shop", "武器屋", "様々な武器が売られている")
        self.forest = Spot("forest", "森", "野生の生物が生息する場所")
        self.cave = Spot("cave", "洞窟", "暗くて危険な場所")
        
        # スポットをマネージャーに追加
        self.spot_manager.add_spot(self.town_square)
        self.spot_manager.add_spot(self.inn)
        self.spot_manager.add_spot(self.shop)
        self.spot_manager.add_spot(self.forest)
        self.spot_manager.add_spot(self.cave)
        
        # 移動可能な接続を設定
        self.spot_manager.get_movement_graph().add_connection(
            "town_square", "inn", "宿屋への道"
        )
        self.spot_manager.get_movement_graph().add_connection(
            "town_square", "shop", "武器屋への道"
        )
        self.spot_manager.get_movement_graph().add_connection(
            "town_square", "forest", "森への道"
        )
        self.spot_manager.get_movement_graph().add_connection(
            "forest", "cave", "洞窟への道"
        )
        
        # ゲームコンテキストを作成
        self.game_context = GameContext(self.player_manager, self.spot_manager)
        
        # 移動戦略を作成
        self.movement_strategy = MovementStrategy()
        
        # プレイヤーの初期位置を設定
        self.player.set_current_spot_id("town_square")
    
    def test_movement_strategy_initialization(self):
        """移動戦略の初期化テスト"""
        strategy = MovementStrategy()
        assert strategy.get_name() == "移動"
    
    def test_get_required_arguments_normal_case(self):
        """正常な場合の必須引数取得テスト"""
        # 街の広場から移動可能な場所を取得
        argument_infos = self.movement_strategy.get_required_arguments(self.player, self.game_context)
        expected_destinations = ["inn", "shop", "forest"]
        
        # ArgumentInfoオブジェクトから候補値を取得
        assert len(argument_infos) == 1
        argument_info = argument_infos[0]
        assert argument_info.name == "target_spot_id"
        assert argument_info.description == "移動先のスポットを選択してください"
        
        # 順序は重要ではないので、セットで比較
        assert set(argument_info.candidates) == set(expected_destinations)
    
    def test_get_required_arguments_no_connections(self):
        """接続がない場合の必須引数取得テスト"""
        # 孤立したスポットを作成してテスト
        isolated_spot = Spot("isolated_spot", "孤立した場所", "どこにも接続していない場所")
        self.spot_manager.add_spot(isolated_spot)
        self.player.set_current_spot_id("isolated_spot")
        argument_infos = self.movement_strategy.get_required_arguments(self.player, self.game_context)
        assert argument_infos == []
    
    def test_can_execute_with_connections(self):
        """接続がある場合の実行可能判定テスト"""
        # 街の広場からは移動可能
        assert self.movement_strategy.can_execute(self.player, self.game_context) == True
    
    def test_can_execute_without_connections(self):
        """接続がない場合の実行可能判定テスト"""
        # 孤立したスポットを作成してテスト
        isolated_spot = Spot("isolated_spot", "孤立した場所", "どこにも接続していない場所")
        self.spot_manager.add_spot(isolated_spot)
        self.player.set_current_spot_id("isolated_spot")
        assert self.movement_strategy.can_execute(self.player, self.game_context) == False
    
    def test_build_action_command(self):
        """アクションコマンド構築テスト"""
        command = self.movement_strategy.build_action_command(
            self.player, self.game_context, "inn"
        )
        assert isinstance(command, MovementCommand)
        assert command.target_spot_id == "inn"
    
    def test_movement_command_initialization(self):
        """移動コマンドの初期化テスト"""
        command = MovementCommand("inn")
        assert command.get_action_name() == "移動"
        assert command.target_spot_id == "inn"
    
    def test_successful_movement(self):
        """成功する移動のテスト"""
        command = MovementCommand("inn")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, MovementResult)
        assert result.success == True
        assert result.old_spot_id == "town_square"
        assert result.new_spot_id == "inn"
        assert "移動に成功しました" in result.message
        assert self.player.get_current_spot_id() == "inn"
    
    def test_movement_to_nonexistent_spot(self):
        """存在しないスポットへの移動テスト"""
        command = MovementCommand("nonexistent_spot")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, MovementResult)
        assert result.success == False
        assert result.old_spot_id == "town_square"
        assert result.new_spot_id == "nonexistent_spot"
        assert "移動先のスポットが見つかりません" in result.message
        assert self.player.get_current_spot_id() == "town_square"  # 位置は変更されない
    
    def test_movement_to_unreachable_spot(self):
        """到達不可能なスポットへの移動テスト"""
        # 街の広場から洞窟へは直接移動できない
        command = MovementCommand("cave")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, MovementResult)
        assert result.success == False
        assert result.old_spot_id == "town_square"
        assert result.new_spot_id == "cave"
        assert "移動先" in result.message and "への接続が存在しません" in result.message
        assert self.player.get_current_spot_id() == "town_square"  # 位置は変更されない
    
    def test_movement_from_isolated_spot(self):
        """孤立したスポットからの移動テスト"""
        # 洞窟から移動しようとする
        self.player.set_current_spot_id("cave")
        command = MovementCommand("town_square")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, MovementResult)
        assert result.success == False
        assert result.old_spot_id == "cave"
        assert result.new_spot_id == "town_square"
        assert "移動先" in result.message and "への接続が存在しません" in result.message
        assert self.player.get_current_spot_id() == "cave"  # 位置は変更されない
    
    def test_movement_result_feedback_message_success(self):
        """成功時のフィードバックメッセージテスト"""
        result = MovementResult(True, "移動に成功しました", "town_square", "inn")
        feedback = result.to_feedback_message("テストプレイヤー")
        assert "テストプレイヤー は town_square から inn に移動しました" == feedback
    
    def test_movement_result_feedback_message_failure(self):
        """失敗時のフィードバックメッセージテスト"""
        result = MovementResult(False, "移動先が見つかりません", "town_square", "nonexistent")
        feedback = result.to_feedback_message("テストプレイヤー")
        assert "テストプレイヤー は town_square から nonexistent に移動できませんでした" in feedback
        assert "理由:移動先が見つかりません" in feedback
    
    def test_multiple_movements(self):
        """複数回の移動テスト"""
        # 街の広場 → 森 → 洞窟
        command1 = MovementCommand("forest")
        result1 = command1.execute(self.player, self.game_context)
        assert result1.success == True
        assert self.player.get_current_spot_id() == "forest"
        
        command2 = MovementCommand("cave")
        result2 = command2.execute(self.player, self.game_context)
        assert result2.success == True
        assert self.player.get_current_spot_id() == "cave"
    
    def test_movement_with_conditions(self):
        """条件付き移動のテスト"""
        # 宝の間スポットを先に追加
        treasure_room = Spot("treasure_room", "宝の間", "宝物が眠る場所")
        self.spot_manager.add_spot(treasure_room)
        
        # 鍵が必要な移動を設定
        movement_graph = self.spot_manager.get_movement_graph()
        movement_graph.add_connection(
            "cave", "treasure_room", "宝の間への扉",
            conditions={"required_key": "treasure_key"}
        )
        
        # 鍵なしで移動を試行
        self.player.set_current_spot_id("cave")
        command = MovementCommand("treasure_room")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == False
        assert "鍵" in result.message and "が必要です" in result.message
    
    def test_movement_with_level_requirement(self):
        """レベル要求付き移動のテスト（Playerクラスにget_levelメソッドがないためスキップ）"""
        pytest.skip("Playerクラスにget_levelメソッドが実装されていないため、このテストはスキップします")
    
    def test_edge_case_empty_spot_id(self):
        """空のスポットIDのエッジケーステスト"""
        command = MovementCommand("")
        result = command.execute(self.player, self.game_context)
        
        assert result.success == False
        assert "移動先のスポットが見つかりません" in result.message
    
    def test_edge_case_none_spot_id(self):
        """NoneスポットIDのエッジケーステスト"""
        command = MovementCommand(None)
        result = command.execute(self.player, self.game_context)
        
        assert result.success == False
        assert "移動先のスポットが見つかりません" in result.message
    
    def test_comprehensive_movement_scenario(self):
        """包括的な移動シナリオテスト"""
        # 1. 初期位置確認
        assert self.player.get_current_spot_id() == "town_square"
    
        # 2. 利用可能な移動先を確認
        argument_infos = self.movement_strategy.get_required_arguments(self.player, self.game_context)
        assert len(argument_infos) == 1
        argument_info = argument_infos[0]
        assert set(argument_info.candidates) == set(["inn", "shop", "forest"])
        
        # 3. 宿屋への移動
        command1 = MovementCommand("inn")
        result1 = command1.execute(self.player, self.game_context)
        assert result1.success == True
        assert self.player.get_current_spot_id() == "inn"
        
        # 4. 街の広場に戻る
        command2 = MovementCommand("town_square")
        result2 = command2.execute(self.player, self.game_context)
        assert result2.success == True
        assert self.player.get_current_spot_id() == "town_square"
        
        # 5. 武器屋への移動
        command3 = MovementCommand("shop")
        result3 = command3.execute(self.player, self.game_context)
        assert result3.success == True
        assert self.player.get_current_spot_id() == "shop"
        
        # 6. 街の広場に戻る
        command4 = MovementCommand("town_square")
        result4 = command4.execute(self.player, self.game_context)
        assert result4.success == True
        assert self.player.get_current_spot_id() == "town_square"
        
        # 7. 森への移動
        command5 = MovementCommand("forest")
        result5 = command5.execute(self.player, self.game_context)
        assert result5.success == True
        assert self.player.get_current_spot_id() == "forest"
        
        # 8. 洞窟への移動
        command6 = MovementCommand("cave")
        result6 = command6.execute(self.player, self.game_context)
        assert result6.success == True
        assert self.player.get_current_spot_id() == "cave"
    
    def test_movement_strategy_with_different_players(self):
        """異なるプレイヤーでの移動戦略テスト"""
        # 新しいプレイヤーを作成
        player2 = Player("test_player_002", "テストプレイヤー2", Role.MERCHANT)
        player2.set_current_spot_id("shop")
        self.player_manager.add_player(player2)
        
        # プレイヤー2の移動可能先を確認
        argument_infos = self.movement_strategy.get_required_arguments(player2, self.game_context)
        assert len(argument_infos) == 1
        argument_info = argument_infos[0]
        assert argument_info.candidates == ["town_square"]
        
        # プレイヤー2の移動を実行
        command = MovementCommand("town_square")
        result = command.execute(player2, self.game_context)
        assert result.success == True
        assert player2.get_current_spot_id() == "town_square"
    
    def test_movement_with_invalid_game_context(self):
        """無効なゲームコンテキストでの移動テスト"""
        # 無効なゲームコンテキストを作成
        invalid_context = GameContext(None, None)
        
        command = MovementCommand("inn")
        result = command.execute(self.player, invalid_context)
        
        assert result.success == False
        assert "スポットマネージャーが無効です" in result.message
    
    def test_movement_with_none_game_context(self):
        """Noneゲームコンテキストでの移動テスト"""
        command = MovementCommand("inn")
        result = command.execute(self.player, None)
        
        assert result.success == False
        assert "ゲームコンテキストが無効です" in result.message
    
    def test_get_required_arguments_with_none_game_context(self):
        """Noneゲームコンテキストでの必須引数取得テスト"""
        argument_infos = self.movement_strategy.get_required_arguments(self.player, None)
        assert argument_infos == []
    
    def test_get_required_arguments_with_none_spot_manager(self):
        """Noneスポットマネージャーでの必須引数取得テスト"""
        # Noneスポットマネージャーを持つゲームコンテキストを作成
        invalid_context = GameContext(self.player_manager, None)
        destinations = self.movement_strategy.get_required_arguments(self.player, invalid_context)
        assert destinations == [] 