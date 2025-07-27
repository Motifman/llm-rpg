import pytest
from unittest.mock import Mock, MagicMock
from game.action.actions.home_action import (
    SleepActionStrategy, SleepActionCommand, SleepActionResult,
    WriteDiaryActionStrategy, WriteDiaryActionCommand, WriteDiaryActionResult
)
from game.enums import Permission
from game.player.player import Player
from game.core.game_context import GameContext


class TestHomeActions:
    """家のアクションのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.mock_player = Mock(spec=Player)
        self.mock_player.player_id = "test_player"
        self.mock_player.name = "テストプレイヤー"
        self.mock_player.health = 100
        self.mock_player.max_health = 100
        self.mock_player.mana = 50
        self.mock_player.max_mana = 100
        self.mock_player.experience = 0
        
        # プレイヤーのメソッドをモック
        self.mock_player.restore_health = Mock()
        self.mock_player.restore_mana = Mock()
        self.mock_player.gain_experience = Mock()
        
        self.mock_game_context = Mock(spec=GameContext)
    
    def test_sleep_action_command_execution(self):
        """睡眠コマンドの実行テスト"""
        sleep_command = SleepActionCommand()
        
        result = sleep_command.execute(self.mock_player, self.mock_game_context)
        
        # 結果の確認
        assert isinstance(result, SleepActionResult)
        assert result.success is True
        assert "ベッドで眠り" in result.message
        assert result.health_restored == 50
        assert result.mana_restored == 30
        
        # プレイヤーの状態が更新されているか
        self.mock_player.restore_health.assert_called_once_with(50)
        self.mock_player.restore_mana.assert_called_once_with(30)
    
    def test_sleep_action_result_feedback(self):
        """睡眠アクション結果のフィードバックテスト"""
        result = SleepActionResult(
            success=True,
            message="テストプレイヤーはベッドで眠り、体力を回復しました。",
            health_restored=50,
            mana_restored=30
        )
        
        feedback = result.to_feedback_message("テストプレイヤー")
        assert "テストプレイヤーはベッドで眠り" in feedback
        assert "体力を50" in feedback
        assert "マナを30" in feedback
    
    def test_write_diary_action_command_execution(self):
        """日記を書くコマンドの実行テスト"""
        content = "今日は冒険に行きました。"
        diary_command = WriteDiaryActionCommand(content)
        
        result = diary_command.execute(self.mock_player, self.mock_game_context)
        
        # 結果の確認
        assert isinstance(result, WriteDiaryActionResult)
        assert result.success is True
        assert "日記を書きました" in result.message
        assert result.content == content
        assert result.exp_gained == 10
        
        # プレイヤーの経験値が更新されているか
        self.mock_player.gain_experience.assert_called_once_with(10)
    
    def test_write_diary_action_result_feedback(self):
        """日記を書くアクション結果のフィードバックテスト"""
        result = WriteDiaryActionResult(
            success=True,
            message="テストプレイヤーは日記を書きました。",
            content="今日は冒険に行きました。",
            exp_gained=10
        )
        
        feedback = result.to_feedback_message("テストプレイヤー")
        assert "テストプレイヤーは日記を書きました" in feedback
        assert "経験値を10" in feedback
    
    def test_sleep_action_strategy_build_command(self):
        """睡眠アクション戦略のコマンド構築テスト"""
        sleep_strategy = SleepActionStrategy()
        
        command = sleep_strategy.build_action_command(self.mock_player, self.mock_game_context)
        
        assert isinstance(command, SleepActionCommand)
        assert command.get_action_name() == "睡眠"
    
    def test_write_diary_action_strategy_build_command(self):
        """日記を書くアクション戦略のコマンド構築テスト"""
        diary_strategy = WriteDiaryActionStrategy()
        
        command = diary_strategy.build_action_command(
            self.mock_player, 
            self.mock_game_context, 
            content="今日は冒険に行きました。"
        )
        
        assert isinstance(command, WriteDiaryActionCommand)
        assert command.get_action_name() == "日記を書く"
        assert command.content == "今日は冒険に行きました。" 