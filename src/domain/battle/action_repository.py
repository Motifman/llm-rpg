from typing import List, Optional, Protocol, TYPE_CHECKING
from src.domain.battle.battle_enum import ActionType
from src.domain.player.player_enum import Role

if TYPE_CHECKING:
    from src.domain.battle.battle_action import BattleAction


class ActionRepository(Protocol):
    """戦闘Actionのリポジトリインターフェース"""

    def find_by_id(self, action_id: int) -> Optional["BattleAction"]:
        """Action IDでActionを取得"""
        ...

    def find_by_ids(self, action_ids: List[int]) -> List["BattleAction"]:
        """複数のAction IDでActionを取得"""
        ...

    def get_all_actions(self) -> List["BattleAction"]:
        """全てのActionを取得"""
        ...

    def get_basic_actions(self) -> List["BattleAction"]:
        """基本Actionを取得（全プレイヤーが最初から使えるAction）"""
        ...

    def get_actions_by_type(self, action_type: ActionType) -> List["BattleAction"]:
        """Actionタイプでフィルタリング"""
        ...
    
    def get_evolution_chain(self, action_id: int) -> List[int]:
        """進化チェーンを取得（基本形から最終進化まで）"""
        ...
    
    def get_action_cost(self, action_id: int) -> int:
        """アクションのキャパシティコストを取得"""
        ...
    
    def get_learnable_actions(self, level: int, role: Role) -> List[int]:
        """指定されたレベルと職業で習得可能なアクションIDを取得"""
        ...
    
    def get_evolution_requirements(self, action_id: int) -> Optional[tuple[int, int]]:
        """進化に必要な条件を取得（経験値、レベル）。進化できない場合はNone"""
        ...
    
    def get_evolved_action_id(self, action_id: int) -> Optional[int]:
        """進化後のアクションIDを取得。進化できない場合はNone"""
        ...
    
    def is_basic_action(self, action_id: int) -> bool:
        """基本アクション（全員が最初から使える）かどうか"""
        ...

    def generate_action_id(self) -> int:
        """アクションIDを生成"""
        ...