import pytest
from unittest.mock import Mock, MagicMock
from game.action.actions.permission_checked_action import PermissionCheckedActionStrategy
from game.action.actions.home_action import SleepActionStrategy, WriteDiaryActionStrategy
from game.enums import Permission
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.special_spot import SpecialSpot


class TestPermissionCheckedActionStrategy:
    """PermissionCheckedActionStrategyのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.mock_player = Mock(spec=Player)
        self.mock_player.player_id = "test_player"
        self.mock_player.name = "テストプレイヤー"
        
        self.mock_game_context = Mock(spec=GameContext)
        self.mock_spot_manager = Mock()
        self.mock_game_context.get_spot_manager.return_value = self.mock_spot_manager
    
    def test_can_execute_with_special_spot(self):
        """SpecialSpotでの権限チェックテスト"""
        # SpecialSpotを作成
        special_spot = SpecialSpot("test_spot", "テストスポット", "テスト用")
        special_spot.set_player_permission("test_player", Permission.OWNER)
        
        self.mock_spot_manager.get_spot.return_value = special_spot
        self.mock_player.get_current_spot_id.return_value = "test_spot"
        
        # OWNER権限が必要なアクション
        sleep_action = SleepActionStrategy()
        
        # OWNER権限を持つプレイヤーは実行可能
        assert sleep_action.can_execute(self.mock_player, self.mock_game_context)
        
        # GUEST権限のプレイヤーは実行不可
        special_spot.set_player_permission("test_player", Permission.GUEST)
        assert not sleep_action.can_execute(self.mock_player, self.mock_game_context)
    
    def test_can_execute_with_normal_spot(self):
        """通常のSpotでの権限チェックテスト"""
        # 通常のSpotを作成（SpecialSpotではない）
        normal_spot = Mock()
        normal_spot.spot_id = "normal_spot"
        
        self.mock_spot_manager.get_spot.return_value = normal_spot
        self.mock_player.get_current_spot_id.return_value = "normal_spot"
        
        # 通常のSpotでは権限チェックなしで実行可能
        sleep_action = SleepActionStrategy()
        assert sleep_action.can_execute(self.mock_player, self.mock_game_context)
    
    def test_sleep_action_strategy(self):
        """睡眠アクションのテスト"""
        sleep_action = SleepActionStrategy()
        
        assert sleep_action.get_name() == "睡眠"
        assert sleep_action.required_permission == Permission.OWNER
        
        # 引数不要
        args = sleep_action.get_required_arguments(self.mock_player, self.mock_game_context)
        assert len(args) == 0
    
    def test_write_diary_action_strategy(self):
        """日記を書くアクションのテスト"""
        diary_action = WriteDiaryActionStrategy()
        
        assert diary_action.get_name() == "日記を書く"
        assert diary_action.required_permission == Permission.OWNER
        
        # content引数が必要
        args = diary_action.get_required_arguments(self.mock_player, self.mock_game_context)
        assert len(args) == 1
        assert args[0].name == "content"
        assert args[0].description == "日記の内容" 