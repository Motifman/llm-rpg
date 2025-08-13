import pytest
from unittest.mock import Mock
from game.world.spots.home_spot import HomeSpot
from game.enums import Permission


class TestHomeSpot:
    """HomeSpotのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.home_spot = HomeSpot("home_spot", "owner_player")
    
    def test_initialization(self):
        """初期化のテスト"""
        assert self.home_spot.spot_id == "home_spot"
        assert self.home_spot.name == "家"
        assert self.home_spot.description == "家、ベッドと机がある"
        
        # オーナーの権限が設定されているか
        assert self.home_spot.get_player_permission("owner_player") == Permission.OWNER
    
    def test_permission_actions_setup(self):
        """権限別アクションの設定テスト"""
        owner_actions = self.home_spot.permission_actions.get(Permission.OWNER, [])
        assert "睡眠" in owner_actions
        assert "日記を書く" in owner_actions
    
    def test_action_strategies_added(self):
        """ActionStrategyが追加されているかテスト"""
        possible_actions = self.home_spot.get_possible_actions()
        action_names = [action.get_name() for action in possible_actions.values()]
        
        assert "睡眠" in action_names
        assert "日記を書く" in action_names
    
    def test_owner_can_access_all_actions(self):
        """オーナーが全てのアクションにアクセスできるかテスト"""
        owner_actions = self.home_spot.get_available_actions_for_player("owner_player")
        action_names = [action.get_name() for action in owner_actions.values()]
        
        assert "睡眠" in action_names
        assert "日記を書く" in action_names
    
    def test_guest_cannot_access_owner_actions(self):
        """ゲストがオーナー専用アクションにアクセスできないかテスト"""
        # ゲストプレイヤーを追加
        self.home_spot.set_player_permission("guest_player", Permission.GUEST)
        
        guest_actions = self.home_spot.get_available_actions_for_player("guest_player")
        action_names = [action.get_name() for action in guest_actions.values()]
        
        # ゲストはオーナー専用アクションにアクセスできない
        assert "睡眠" not in action_names
        assert "日記を書く" not in action_names
    
    def test_inheritance_from_special_spot(self):
        """SpecialSpotからの継承のテスト"""
        # SpecialSpotの機能が使えることを確認
        assert hasattr(self.home_spot, 'permission_manager')
        assert hasattr(self.home_spot, 'permission_actions')
        assert hasattr(self.home_spot, 'set_player_permission')
        assert hasattr(self.home_spot, 'get_available_actions_for_player') 