from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING
from game.player.player import Player

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.action.action_command import ActionCommand
    from game.core.game_context import GameContext


class ActionStrategy(ABC):
    def __init__(self, action_name: str):
        self.action_name = action_name
        
    def get_name(self) -> str:
        return self.action_name
    
    @abstractmethod
    def get_required_arguments(self, acting_player: Player, game_context: 'GameContext') -> List[str]:
        pass
    
    @abstractmethod
    def can_execute(self, acting_player: Player, game_context: 'GameContext') -> bool:
        pass
    
    @abstractmethod
    def build_action_command(self, acting_player: Player, game_context: 'GameContext', **kwargs) -> 'ActionCommand':
        pass