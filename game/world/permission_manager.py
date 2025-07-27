from typing import Dict, Optional, List
from game.enums import Permission


class PermissionManager:
    """権限管理システム"""
    
    def __init__(self):
        self.player_permissions: Dict[str, Permission] = {}
        self.default_permission = Permission.GUEST
    
    def set_player_permission(self, player_id: str, permission: Permission):
        """プレイヤーの権限を設定"""
        self.player_permissions[player_id] = permission
    
    def get_player_permission(self, player_id: str) -> Permission:
        """プレイヤーの権限を取得（デフォルトはGUEST）"""
        return self.player_permissions.get(player_id, self.default_permission)
    
    def remove_player_permission(self, player_id: str):
        """プレイヤーの権限を削除（デフォルトに戻る）"""
        if player_id in self.player_permissions:
            del self.player_permissions[player_id]
    
    def get_players_with_permission(self, permission: Permission) -> List[str]:
        """特定の権限を持つプレイヤー一覧を取得"""
        return [pid for pid, perm in self.player_permissions.items() if perm == permission]
    
    def has_permission(self, player_id: str, required_permission: Permission) -> bool:
        """プレイヤーが指定された権限を持っているかチェック"""
        player_permission = self.get_player_permission(player_id)
        return self._check_permission_hierarchy(player_permission, required_permission)
    
    def _check_permission_hierarchy(self, player_permission: Permission, required_permission: Permission) -> bool:
        """権限の階層チェック"""
        permission_hierarchy = {
            Permission.OWNER: 4,
            Permission.EMPLOYEE: 3,
            Permission.CUSTOMER: 2,
            Permission.MEMBER: 2,
            Permission.GUEST: 1,
            Permission.DENIED: 0
        }
        
        player_level = permission_hierarchy.get(player_permission, 0)
        required_level = permission_hierarchy.get(required_permission, 0)
        
        return player_level >= required_level 