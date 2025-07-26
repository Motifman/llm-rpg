from abc import ABC, abstractmethod
from typing import List, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from game.player.player import Player

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.action.action_command import ActionCommand
    from game.core.game_context import GameContext


@dataclass
class ArgumentInfo:
    """アクション実行に必要な引数の情報を表すクラス"""
    name: str  # 引数名
    description: str  # 引数の説明
    candidates: Optional[List[str]] = None  # 候補値のリスト（Noneの場合は自由入力）


class ActionStrategy(ABC):
    def __init__(self, action_name: str):
        self.action_name = action_name
        
    def get_name(self) -> str:
        return self.action_name
    
    @abstractmethod
    def get_required_arguments(self, acting_player: Player, game_context: 'GameContext') -> List[ArgumentInfo]:
        pass
    
    @abstractmethod
    def can_execute(self, acting_player: Player, game_context: 'GameContext') -> bool:
        pass
    
    @abstractmethod
    def build_action_command(self, acting_player: Player, game_context: 'GameContext', **kwargs) -> 'ActionCommand':
        pass