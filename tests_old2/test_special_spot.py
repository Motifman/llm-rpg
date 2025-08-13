import pytest
from unittest.mock import Mock
from game.world.special_spot import SpecialSpot
from game.enums import Permission
from game.action.action_strategy import ActionStrategy


class MockActionStrategy(ActionStrategy):
    """テスト用のモックActionStrategy"""
    
    def __init__(self, name: str):
        super().__init__(name)
    
    def get_required_arguments(self, acting_player, game_context):
        return []
    
    def can_execute(self, acting_player, game_context):
        return True
    
    def build_action_command(self, acting_player, game_context, **kwargs):
        return Mock()


class TestSpecialSpot:
    """SpecialSpotのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.special_spot = SpecialSpot("test_spot", "テストスポット", "テスト用のスポットです")
    
    def test_initialization(self):
        """初期化のテスト"""
        assert self.special_spot.spot_id == "test_spot"
        assert self.special_spot.name == "テストスポット"
        assert self.special_spot.description == "テスト用のスポットです"
        assert hasattr(self.special_spot, 'permission_manager')
        assert hasattr(self.special_spot, 'permission_actions')
    
    def test_set_player_permission(self):
        """プレイヤー権限設定のテスト"""
        self.special_spot.set_player_permission("player1", Permission.OWNER)
        assert self.special_spot.get_player_permission("player1") == Permission.OWNER
    
    def test_default_permission(self):
        """デフォルト権限のテスト"""
        assert self.special_spot.get_player_permission("player1") == Permission.GUEST
    
    def test_add_permission_action(self):
        """権限別アクション追加のテスト"""
        self.special_spot.add_permission_action(Permission.OWNER, ["睡眠", "日記を書く"])
        self.special_spot.add_permission_action(Permission.GUEST, ["見学"])
        
        assert "睡眠" in self.special_spot.permission_actions[Permission.OWNER]
        assert "日記を書く" in self.special_spot.permission_actions[Permission.OWNER]
        assert "見学" in self.special_spot.permission_actions[Permission.GUEST]
    
    def test_get_available_actions_for_player(self):
        """プレイヤーが利用可能なアクション取得のテスト"""
        # モックActionStrategyを追加
        sleep_action = MockActionStrategy("睡眠")
        diary_action = MockActionStrategy("日記を書く")
        self.special_spot.add_action(sleep_action)
        self.special_spot.add_action(diary_action)
        
        # 権限別アクションを設定
        self.special_spot.add_permission_action(Permission.OWNER, ["睡眠", "日記を書く"])
        self.special_spot.add_permission_action(Permission.GUEST, ["睡眠"])
        
        # オーナーの場合
        self.special_spot.set_player_permission("owner", Permission.OWNER)
        owner_actions = self.special_spot.get_available_actions_for_player("owner")
        assert len(owner_actions) == 2
        assert "睡眠" in owner_actions
        assert "日記を書く" in owner_actions
        
        # ゲストの場合
        self.special_spot.set_player_permission("guest", Permission.GUEST)
        guest_actions = self.special_spot.get_available_actions_for_player("guest")
        assert len(guest_actions) == 1
        assert "睡眠" in guest_actions
        assert "日記を書く" not in guest_actions
    
    def test_inheritance_from_spot(self):
        """Spotクラスからの継承のテスト"""
        # 基本的なSpotの機能が使えることを確認
        assert hasattr(self.special_spot, 'add_interactable')
        assert hasattr(self.special_spot, 'get_possible_actions')
        assert hasattr(self.special_spot, 'add_action') 