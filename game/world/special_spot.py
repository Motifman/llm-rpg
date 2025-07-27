from typing import Dict, List, Optional
from game.enums import Permission
from game.action.action_strategy import ActionStrategy
from game.world.spot import Spot
from game.world.permission_manager import PermissionManager


class SpecialSpot(Spot):
    """権限ベースのアクションを持つ特殊なSpot"""
    
    def __init__(self, spot_id: str, name: str, description: str):
        super().__init__(spot_id, name, description)
        self.permission_manager = PermissionManager()
        # 権限別アクションの定義（Spot固有の行動のみ）
        self.permission_actions: Dict[Permission, List[str]] = {}
    
    def set_player_permission(self, player_id: str, permission: Permission):
        """プレイヤーの権限を設定"""
        self.permission_manager.set_player_permission(player_id, permission)
    
    def add_permission_action(self, permission: Permission, action_names: List[str]):
        """権限に応じたSpot固有アクションを追加"""
        if permission not in self.permission_actions:
            self.permission_actions[permission] = []
        self.permission_actions[permission].extend(action_names)
    
    def get_player_permission(self, player_id: str) -> Permission:
        """プレイヤーの権限を取得（デフォルトはGUEST）"""
        return self.permission_manager.get_player_permission(player_id)
    
    def get_possible_actions(self) -> Dict[str, 'ActionStrategy']:
        """既存のSpot.get_possible_actions()をオーバーライド"""
        # 通常のSpotの行動を取得
        base_actions = super().get_possible_actions()
        
        # SpecialSpotの場合は、権限に応じたSpot固有の行動を追加
        # この時点では全ての利用可能な行動を返す（権限チェックはActionStrategy側で行う）
        return base_actions
    
    def get_available_actions_for_player(self, player_id: str) -> Dict[str, 'ActionStrategy']:
        """プレイヤーが利用可能なSpot固有のアクションを取得"""
        permission = self.get_player_permission(player_id)
        available_action_names = self.permission_actions.get(permission, [])
        
        available_actions = {}
        for action_name in available_action_names:
            # 既存の_possible_actionsから該当するActionStrategyを取得
            if action_name in self._possible_actions:
                available_actions[action_name] = self._possible_actions[action_name]
        
        return available_actions 