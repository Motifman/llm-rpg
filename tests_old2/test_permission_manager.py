import pytest
from game.world.permission_manager import PermissionManager
from game.enums import Permission


class TestPermissionManager:
    """PermissionManagerのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.permission_manager = PermissionManager()
    
    def test_default_permission(self):
        """デフォルト権限のテスト"""
        # デフォルトはGUEST
        assert self.permission_manager.get_player_permission("player1") == Permission.GUEST
    
    def test_set_player_permission(self):
        """プレイヤー権限設定のテスト"""
        self.permission_manager.set_player_permission("player1", Permission.OWNER)
        assert self.permission_manager.get_player_permission("player1") == Permission.OWNER
    
    def test_remove_player_permission(self):
        """プレイヤー権限削除のテスト"""
        self.permission_manager.set_player_permission("player1", Permission.OWNER)
        self.permission_manager.remove_player_permission("player1")
        assert self.permission_manager.get_player_permission("player1") == Permission.GUEST
    
    def test_get_players_with_permission(self):
        """特定権限を持つプレイヤー一覧取得のテスト"""
        self.permission_manager.set_player_permission("player1", Permission.OWNER)
        self.permission_manager.set_player_permission("player2", Permission.OWNER)
        self.permission_manager.set_player_permission("player3", Permission.GUEST)
        
        owners = self.permission_manager.get_players_with_permission(Permission.OWNER)
        assert len(owners) == 2
        assert "player1" in owners
        assert "player2" in owners
    
    def test_has_permission_hierarchy(self):
        """権限階層チェックのテスト"""
        self.permission_manager.set_player_permission("owner", Permission.OWNER)
        self.permission_manager.set_player_permission("employee", Permission.EMPLOYEE)
        self.permission_manager.set_player_permission("customer", Permission.CUSTOMER)
        self.permission_manager.set_player_permission("guest", Permission.GUEST)
        self.permission_manager.set_player_permission("denied", Permission.DENIED)
        
        # OWNERは全ての権限を持つ
        assert self.permission_manager.has_permission("owner", Permission.OWNER)
        assert self.permission_manager.has_permission("owner", Permission.EMPLOYEE)
        assert self.permission_manager.has_permission("owner", Permission.CUSTOMER)
        assert self.permission_manager.has_permission("owner", Permission.GUEST)
        
        # EMPLOYEEはOWNER以外の権限を持つ
        assert not self.permission_manager.has_permission("employee", Permission.OWNER)
        assert self.permission_manager.has_permission("employee", Permission.EMPLOYEE)
        assert self.permission_manager.has_permission("employee", Permission.CUSTOMER)
        assert self.permission_manager.has_permission("employee", Permission.GUEST)
        
        # CUSTOMERはEMPLOYEE以下
        assert not self.permission_manager.has_permission("customer", Permission.OWNER)
        assert not self.permission_manager.has_permission("customer", Permission.EMPLOYEE)
        assert self.permission_manager.has_permission("customer", Permission.CUSTOMER)
        assert self.permission_manager.has_permission("customer", Permission.GUEST)
        
        # GUESTはCUSTOMER以下
        assert not self.permission_manager.has_permission("guest", Permission.OWNER)
        assert not self.permission_manager.has_permission("guest", Permission.EMPLOYEE)
        assert not self.permission_manager.has_permission("guest", Permission.CUSTOMER)
        assert self.permission_manager.has_permission("guest", Permission.GUEST)
        
        # DENIEDは何もできない
        assert not self.permission_manager.has_permission("denied", Permission.OWNER)
        assert not self.permission_manager.has_permission("denied", Permission.EMPLOYEE)
        assert not self.permission_manager.has_permission("denied", Permission.CUSTOMER)
        assert not self.permission_manager.has_permission("denied", Permission.GUEST) 