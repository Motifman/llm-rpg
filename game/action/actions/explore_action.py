from typing import List
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy
from game.player.player import Player
from game.core.game_context import GameContext


class ExploreActionResult(ActionResult):
    def __init__(self, success: bool, message: str, exploration_summary: str):
        super().__init__(success, message)
        self.exploration_summary = exploration_summary

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は周囲を探索しました\n\t探索結果:{self.exploration_summary}"
        else:
            return f"{player_name} は探索に失敗しました\n\t理由:{self.message}"


class ExploreActionStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("探索")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        return []
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return ExploreActionCommand()


class ExploreActionCommand(ActionCommand):
    def __init__(self):
        super().__init__("探索")

    def execute(self, acting_player: Player, game_context: GameContext) -> ExploreActionResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        return ExploreActionResult(True, "探索しました", current_spot.get_exploration_summary())