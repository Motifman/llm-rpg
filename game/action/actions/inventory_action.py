from typing import List
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy
from game.player.player import Player
from game.core.game_context import GameContext


class InventoryCheckResult(ActionResult):
    def __init__(self, success: bool, message: str, inventory_summary: str):
        super().__init__(success, message)
        self.inventory_summary = inventory_summary

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} の所持アイテムを確認しました\n\t所持アイテム:{self.inventory_summary}"
        else:
            return f"{player_name} の所持アイテムを確認できませんでした\n\t理由:{self.message}"


class InventoryCheckStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("所持アイテム確認")
        
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        return []
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True
    
    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return InventoryCheckCommand()


class InventoryCheckCommand(ActionCommand):
    def __init__(self):
        super().__init__("所持アイテム確認")

    def execute(self, acting_player: Player, game_context: GameContext) -> InventoryCheckResult:
        inventory = acting_player.get_inventory()
        inventory_summary = inventory.get_summary()
        return InventoryCheckResult(True, "所持アイテムを確認しました", inventory_summary)