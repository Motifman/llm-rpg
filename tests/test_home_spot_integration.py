import pytest
from unittest.mock import Mock, MagicMock
from game.world.spots.home_spot import HomeSpot
from game.action.actions.home_action import SleepActionStrategy, WriteDiaryActionStrategy
from game.enums import Permission
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager


class TestHomeSpotIntegration:
    """HomeSpotの統合テスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        # プレイヤーの作成
        self.player = Mock(spec=Player)
        self.player.player_id = "owner_player"
        self.player.name = "オーナー"
        self.player.health = 80
        self.player.max_health = 100
        self.player.mana = 30
        self.player.max_mana = 100
        self.player.experience = 0
        
        # プレイヤーのメソッドをモック
        self.player.restore_health = Mock()
        self.player.restore_mana = Mock()
        self.player.gain_experience = Mock()
        self.player.get_current_spot_id = Mock(return_value="home_spot")
        
        # ゲストプレイヤーの作成
        self.guest_player = Mock(spec=Player)
        self.guest_player.player_id = "guest_player"
        self.guest_player.name = "ゲスト"
        self.guest_player.get_current_spot_id = Mock(return_value="home_spot")
        
        # GameContextの作成
        self.game_context = Mock(spec=GameContext)
        self.spot_manager = Mock(spec=SpotManager)
        self.game_context.get_spot_manager.return_value = self.spot_manager
        
        # HomeSpotの作成
        self.home_spot = HomeSpot("home_spot", "owner_player")
        self.spot_manager.get_spot.return_value = self.home_spot
    
    def test_owner_can_sleep(self):
        """オーナーが睡眠できるかテスト"""
        sleep_strategy = SleepActionStrategy()
        
        # 権限チェック
        assert sleep_strategy.can_execute(self.player, self.game_context)
        
        # コマンド構築
        command = sleep_strategy.build_action_command(self.player, self.game_context)
        
        # 実行
        result = command.execute(self.player, self.game_context)
        
        # 結果の確認
        assert result.success is True
        assert "ベッドで眠り" in result.message
        self.player.restore_health.assert_called_once_with(50)
        self.player.restore_mana.assert_called_once_with(30)
    
    def test_owner_can_write_diary(self):
        """オーナーが日記を書けるかテスト"""
        diary_strategy = WriteDiaryActionStrategy()
        
        # 権限チェック
        assert diary_strategy.can_execute(self.player, self.game_context)
        
        # コマンド構築
        command = diary_strategy.build_action_command(
            self.player, 
            self.game_context, 
            content="今日は冒険に行きました。"
        )
        
        # 実行
        result = command.execute(self.player, self.game_context)
        
        # 結果の確認
        assert result.success is True
        assert "日記を書きました" in result.message
        self.player.gain_experience.assert_called_once_with(10)
    
    def test_guest_cannot_sleep(self):
        """ゲストが睡眠できないかテスト"""
        # ゲストの権限を設定
        self.home_spot.set_player_permission("guest_player", Permission.GUEST)
        
        sleep_strategy = SleepActionStrategy()
        
        # 権限チェック
        assert not sleep_strategy.can_execute(self.guest_player, self.game_context)
    
    def test_guest_cannot_write_diary(self):
        """ゲストが日記を書けないかテスト"""
        # ゲストの権限を設定
        self.home_spot.set_player_permission("guest_player", Permission.GUEST)
        
        diary_strategy = WriteDiaryActionStrategy()
        
        # 権限チェック
        assert not diary_strategy.can_execute(self.guest_player, self.game_context)
    
    def test_available_actions_for_owner(self):
        """オーナーが利用可能なアクションの確認"""
        available_actions = self.home_spot.get_available_actions_for_player("owner_player")
        action_names = [action.get_name() for action in available_actions.values()]
        
        assert "睡眠" in action_names
        assert "日記を書く" in action_names
    
    def test_available_actions_for_guest(self):
        """ゲストが利用可能なアクションの確認"""
        # ゲストの権限を設定
        self.home_spot.set_player_permission("guest_player", Permission.GUEST)
        
        available_actions = self.home_spot.get_available_actions_for_player("guest_player")
        action_names = [action.get_name() for action in available_actions.values()]
        
        # ゲストはオーナー専用アクションにアクセスできない
        assert "睡眠" not in action_names
        assert "日記を書く" not in action_names
    
    def test_permission_hierarchy(self):
        """権限階層のテスト"""
        # EMPLOYEE権限を持つプレイヤー
        employee_player = Mock(spec=Player)
        employee_player.player_id = "employee_player"
        employee_player.get_current_spot_id = Mock(return_value="home_spot")
        
        self.home_spot.set_player_permission("employee_player", Permission.EMPLOYEE)
        
        sleep_strategy = SleepActionStrategy()
        
        # EMPLOYEEはOWNER権限が必要なアクションを実行できない
        assert not sleep_strategy.can_execute(employee_player, self.game_context) 