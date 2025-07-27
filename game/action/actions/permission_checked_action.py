from abc import ABC
from typing import List
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.action.action_command import ActionCommand
from game.player.player import Player
from game.core.game_context import GameContext
from game.enums import Permission


class PermissionCheckedActionStrategy(ActionStrategy, ABC):
    """権限チェック付きActionStrategyの基底クラス"""
    
    def __init__(self, action_name: str, required_permission: Permission):
        super().__init__(action_name)
        self.required_permission = required_permission
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        """権限チェックを含む実行可能性チェック"""
        current_spot = game_context.get_spot_manager().get_spot(acting_player.get_current_spot_id())
        
        # SpecialSpotの場合のみ権限チェック
        if hasattr(current_spot, 'permission_manager'):
            return current_spot.permission_manager.has_permission(
                acting_player.player_id, 
                self.required_permission
            )
        
        # 通常のSpotの場合は権限チェックなし
        return True 