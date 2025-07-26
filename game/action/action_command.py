from abc import ABC, abstractmethod
from game.action.action_result import ActionResult
from game.player.player import Player
from game.core.game_context import GameContext


class ActionCommand(ABC):
    def __init__(self, action_name: str):
        self.action_name = action_name
    
    def get_action_name(self) -> str:
        return self.action_name

    @abstractmethod
    def execute(self, acting_player: Player, game_context: GameContext) -> ActionResult:
        pass