"""
InMemoryActionRepository - 実際のBattleActionクラスを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Set
from src.domain.battle.action_repository import ActionRepository
from src.domain.battle.battle_action import BattleAction, AttackAction, HealAction, StatusEffectInfo
from src.domain.battle.battle_enum import (
    ActionType, TargetSelectionMethod, Element, StatusEffectType, BuffType
)
from src.domain.player.player_enum import Role


class InMemoryActionRepository(ActionRepository):
    """実際のBattleActionクラスを使用するインメモリリポジトリ"""
    
    def __init__(self):
        self._actions: Dict[int, BattleAction] = {}
        self._action_costs: Dict[int, int] = {}
        self._learnable_actions: Dict[Role, Dict[int, Set[int]]] = {}  # Role -> Level -> ActionIds
        
        # サンプルアクションデータを作成
        self._setup_sample_data()
    
    def _setup_sample_data(self):
        """サンプルアクションデータのセットアップ"""
        # 1. 基本攻撃
        basic_attack = AttackAction(
            action_id=1,
            name="基本攻撃",
            description="通常の物理攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            damage_multiplier=1.0,
            mp_cost=0,
            hp_cost=0
        )
        self._actions[1] = basic_attack
        self._action_costs[1] = 1
        
        # 2. 強攻撃
        power_attack = AttackAction(
            action_id=2,
            name="強攻撃",
            description="威力の高い物理攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            damage_multiplier=1.5,
            mp_cost=5,
            hp_cost=0
        )
        self._actions[2] = power_attack
        self._action_costs[2] = 2
        
        # 3. ファイアボール
        fireball = AttackAction(
            action_id=3,
            name="ファイアボール",
            description="火属性の魔法攻撃",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            damage_multiplier=1.2,
            mp_cost=8,
            hp_cost=0,
            element=Element.FIRE
        )
        self._actions[3] = fireball
        self._action_costs[3] = 2
        
        # 4. ヒール
        heal = HealAction(
            action_id=4,
            name="ヒール",
            description="HPを回復する",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            heal_hp_amount=25,
            mp_cost=6
        )
        self._actions[4] = heal
        self._action_costs[4] = 2
        
        # 5. 全体攻撃（デモ用）
        area_attack = AttackAction(
            action_id=5,
            name="全体攻撃",
            description="敵全体に攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.ALL_ENEMIES,
            damage_multiplier=0.8,
            mp_cost=10,
            hp_cost=0
        )
        self._actions[5] = area_attack
        self._action_costs[5] = 3
        
        # 6. 必殺技（デモ用・全滅攻撃）
        ultimate_attack = AttackAction(
            action_id=6,
            name="必殺技",
            description="敵全体に大ダメージを与える必殺技",
            action_type=ActionType.SPECIAL,
            target_selection_method=TargetSelectionMethod.ALL_ENEMIES,
            damage_multiplier=10.0,  # 確実に倒せる高い倍率
            mp_cost=20,
            hp_cost=0
        )
        self._actions[6] = ultimate_attack
        self._action_costs[6] = 5
        
        # 習得可能アクションの設定
        self._setup_learnable_actions()
    
    def _setup_learnable_actions(self):
        """習得可能アクションの設定"""
        # 冒険者のアクション
        self._learnable_actions[Role.ADVENTURER] = {
            1: {1, 2},      # レベル1: 基本攻撃、強攻撃
            3: {3, 4},      # レベル3: ファイアボール、ヒール
            5: {5},         # レベル5: 全体攻撃
            10: {6},        # レベル10: 必殺技
        }
        
        # 商人のアクション（限定的）
        self._learnable_actions[Role.MERCHANT] = {
            1: {1},         # レベル1: 基本攻撃のみ
            5: {4},         # レベル5: ヒール
        }
        
        # 市民のアクション（基本のみ）
        self._learnable_actions[Role.CITIZEN] = {
            1: {1},         # レベル1: 基本攻撃のみ
        }
    
    def find_by_id(self, action_id: int) -> Optional[BattleAction]:
        """アクションIDでアクションを検索"""
        return self._actions.get(action_id)
    
    def find_by_ids(self, action_ids: List[int]) -> List[BattleAction]:
        """複数のアクションIDでアクションを検索"""
        result = []
        for action_id in action_ids:
            action = self._actions.get(action_id)
            if action:
                result.append(action)
        return result
    
    def find_by_type(self, action_type: ActionType) -> List[BattleAction]:
        """アクションタイプでアクションを検索"""
        return [action for action in self._actions.values()
                if action.action_type == action_type]
    
    def find_by_target_method(self, target_method: TargetSelectionMethod) -> List[BattleAction]:
        """ターゲット選択方法でアクションを検索"""
        return [action for action in self._actions.values()
                if action.target_selection_method == target_method]
    
    def get_learnable_actions(self, level: int, role: Role) -> List[int]:
        """指定されたレベルとロールで習得可能なアクションIDを取得"""
        if role not in self._learnable_actions:
            return []
        
        learnable_action_ids = set()
        role_actions = self._learnable_actions[role]
        
        # 現在のレベル以下で習得可能なアクションを全て取得
        for required_level, action_ids in role_actions.items():
            if level >= required_level:
                learnable_action_ids.update(action_ids)
        
        return list(learnable_action_ids)
    
    def get_action_cost(self, action_id: int) -> int:
        """アクションのコストを取得"""
        return self._action_costs.get(action_id, 1)
    
    def find_all(self) -> List[BattleAction]:
        """全てのアクションを取得"""
        return list(self._actions.values())
    
    def save(self, action: BattleAction) -> None:
        """アクションを保存"""
        self._actions[action.action_id] = action
    
    def delete(self, action_id: int) -> None:
        """アクションを削除"""
        if action_id in self._actions:
            del self._actions[action_id]
        if action_id in self._action_costs:
            del self._action_costs[action_id]
    
    def exists_by_id(self, action_id: int) -> bool:
        """アクションIDが存在するかチェック"""
        return action_id in self._actions
    
    def count(self) -> int:
        """アクションの総数を取得"""
        return len(self._actions)
    
    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのアクションを削除（テスト用）"""
        self._actions.clear()
        self._action_costs.clear()
        self._learnable_actions.clear()
