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
        from game.player.player import Player
        from game.player.status import Status
        from game.enums import Role
        
        # 実際のPlayerオブジェクトを作成
        self.player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
        self.player.status = Status()
        # 初期状態を設定
        self.player.status.set_hp(80)  # 体力を少し減らしておく
        self.player.status.set_mp(30)  # マナを少し減らしておく
        self.player.status.set_experience_points(0)
        
        self.mock_game_context = Mock(spec=GameContext)
    
    def test_sleep_action_command_execution(self):
        """睡眠コマンドの実行テスト"""
        sleep_command = SleepActionCommand()
        
        # 実行前の状態を記録
        initial_hp = self.player.status.get_hp()
        initial_mp = self.player.status.get_mp()
        
        result = sleep_command.execute(self.player, self.mock_game_context)
        
        # 結果の確認
        assert isinstance(result, SleepActionResult)
        assert result.success is True
        assert "ベッドで眠り" in result.message
        
        # 実際の回復量を確認
        final_hp = self.player.status.get_hp()
        final_mp = self.player.status.get_mp()
        actual_hp_restored = final_hp - initial_hp
        actual_mp_restored = final_mp - initial_mp
        
        assert actual_hp_restored > 0
        assert actual_mp_restored > 0
        assert result.health_restored == actual_hp_restored
        assert result.mana_restored == actual_mp_restored
    
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
        
        # 実行前の状態を記録
        initial_exp = self.player.status.get_experience_points()
        
        result = diary_command.execute(self.player, self.mock_game_context)
        
        # 結果の確認
        assert isinstance(result, WriteDiaryActionResult)
        assert result.success is True
        assert "日記を書きました" in result.message
        assert result.content == content
        assert result.exp_gained == 10
        
        # 実際の経験値増加を確認
        final_exp = self.player.status.get_experience_points()
        actual_exp_gained = final_exp - initial_exp
        
        assert actual_exp_gained == 10
    
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
        
        command = sleep_strategy.build_action_command(self.player, self.mock_game_context)
        
        assert isinstance(command, SleepActionCommand)
        assert command.get_action_name() == "睡眠"
    
    def test_write_diary_action_strategy_build_command(self):
        """日記を書くアクション戦略のコマンド構築テスト"""
        diary_strategy = WriteDiaryActionStrategy()
        
        command = diary_strategy.build_action_command(
            self.player, 
            self.mock_game_context, 
            content="今日は冒険に行きました。"
        )
        
        assert isinstance(command, WriteDiaryActionCommand)
        assert command.get_action_name() == "日記を書く"
        assert command.content == "今日は冒険に行きました。" 