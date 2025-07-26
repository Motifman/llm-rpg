from typing import List
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy
from game.player.player import Player
from game.core.game_context import GameContext


class MovementResult(ActionResult):
    def __init__(self, success: bool, message: str, old_spot_id: str, new_spot_id: str):
        super().__init__(success, message)
        self.old_spot_id = old_spot_id
        self.new_spot_id = new_spot_id

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.old_spot_id} から {self.new_spot_id} に移動しました"
        else:
            return f"{player_name} は {self.old_spot_id} から {self.new_spot_id} に移動できませんでした\n\t理由:{self.message}"


class MovementStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("移動")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        current_spot_id = acting_player.get_current_spot_id()
        spot_manager = game_context.get_spot_manager()
        return spot_manager.get_destination_spot_ids(current_spot_id)

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return len(self.get_required_arguments(acting_player, game_context)) > 0

    def build_action_command(self, acting_player: Player, game_context: GameContext, target_spot_id: str) -> ActionCommand:
        return MovementCommand(target_spot_id)
    

class MovementCommand(ActionCommand):
    def __init__(self, target_spot_id: str):
        super().__init__("移動")
        self.target_spot_id = target_spot_id

    def execute(self, acting_player: Player, game_context: GameContext) -> MovementResult:
        old_spot_id = acting_player.get_current_spot_id()
        spot_manager = game_context.get_spot_manager()
        spot = spot_manager.get_spot(self.target_spot_id)
        if spot is None:
            return MovementResult(False, "移動先のスポットが見つかりません", old_spot_id, self.target_spot_id)
        
        movement_validator = spot_manager.get_movement_validator()
        is_valid, errors = movement_validator.validate_movement(old_spot_id, self.target_spot_id, acting_player)
        if not is_valid:
            return MovementResult(False, "\n".join(errors), old_spot_id, self.target_spot_id)
        
        acting_player.set_current_spot_id(self.target_spot_id)
        return MovementResult(True, "移動に成功しました", old_spot_id, self.target_spot_id)