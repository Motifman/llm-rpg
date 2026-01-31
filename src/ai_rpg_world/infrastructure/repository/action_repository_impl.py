from typing import List, Optional, Dict
from ai_rpg_world.domain.battle.action_repository import ActionRepository
from ai_rpg_world.domain.battle.battle_action import BattleAction
from ai_rpg_world.domain.battle.battle_enum import ActionType
from ai_rpg_world.domain.player.player_enum import Role


class ActionRepositoryImpl(ActionRepository):
    """ActionRepositoryの実装クラス"""
    
    def __init__(self):
        # 実際の実装では、データベースやファイルからロードする
        # ここでは簡単な例として辞書で管理
        self._actions: Dict[int, BattleAction] = {}
        self._action_costs: Dict[int, int] = {}
        self._evolution_chains: Dict[int, List[int]] = {}
        self._evolution_requirements: Dict[int, tuple[int, int]] = {}  # (経験値, レベル)
        self._learnable_actions: Dict[tuple[int, Role], List[int]] = {}  # (level, role) -> action_ids
        self._basic_action_ids: set[int] = set()
        
        # 初期データをセットアップ
        self._setup_initial_data()
    
    def _setup_initial_data(self):
        """初期データのセットアップ（実際の実装ではデータベースから取得）"""
        from ai_rpg_world.domain.battle.battle_action import AttackAction, HealAction, DefendAction
        from ai_rpg_world.domain.battle.battle_enum import ActionType, TargetSelectionMethod, Element
        
        # 基本アクション（全プレイヤーが最初から使える）
        self._basic_action_ids = {1, 2, 3}  # 攻撃、防御、アイテム使用など
        
        # アクションデータを作成
        # 1: 基本攻撃
        basic_attack = AttackAction(
            action_id=1,
            name="基本攻撃",
            description="通常の物理攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            damage_multiplier=1.0,
            element=Element.NEUTRAL,
            race_attack_multiplier={}
        )
        self._actions[1] = basic_attack
        
        # 2: 防御
        defend = DefendAction(
            action_id=2,
            name="防御",
            description="次のターンまで防御力を上げる",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SELF
        )
        self._actions[2] = defend
        
        # 3: アイテム使用（簡易版）
        item_use = AttackAction(
            action_id=3,
            name="アイテム使用",
            description="アイテムを使用する",
            action_type=ActionType.SPECIAL,
            target_selection_method=TargetSelectionMethod.SELF,
            damage_multiplier=0.0,
            element=Element.NEUTRAL,
            race_attack_multiplier={}
        )
        self._actions[3] = item_use
        
        # 4: ファイアボール
        fireball = AttackAction(
            action_id=4,
            name="ファイアボール",
            description="炎の魔法攻撃",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            damage_multiplier=1.5,
            element=Element.FIRE,
            race_attack_multiplier={},
            mp_cost=10
        )
        self._actions[4] = fireball
        
        # 6: ヒール
        heal = HealAction(
            action_id=6,
            name="ヒール",
            description="HPを回復する",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            heal_hp_amount=30,
            mp_cost=8
        )
        self._actions[6] = heal
        
        # アクションコスト
        self._action_costs = {
            1: 1,   # 基本攻撃
            2: 1,   # 防御
            3: 1,   # アイテム使用
            4: 2,   # ファイアボール
            5: 3,   # メテオ（ファイアボールの進化）
            6: 2,   # ヒール
            7: 3,   # フルヒール（ヒールの進化）
        }
        
        # 進化チェーン
        self._evolution_chains = {
            4: [4, 5],  # ファイアボール -> メテオ
            5: [4, 5],  # メテオ（最終形）
            6: [6, 7],  # ヒール -> フルヒール
            7: [6, 7],  # フルヒール（最終形）
        }
        
        # 進化要件（経験値、レベル）
        self._evolution_requirements = {
            4: (100, 3),  # ファイアボール -> メテオ
            6: (80, 2),   # ヒール -> フルヒール
        }
        
        # 習得可能アクション（レベル、職業別）
        self._learnable_actions = {
            (1, Role.ADVENTURER): [1, 2, 3],
            (1, Role.ALCHEMIST): [1, 2, 3, 4, 6],
            (1, Role.PRIEST): [1, 2, 3, 6],
            (3, Role.ALCHEMIST): [1, 2, 3, 4, 6],
            (5, Role.ALCHEMIST): [1, 2, 3, 4, 5, 6, 7],
        }
    
    def find_by_id(self, action_id: int) -> Optional[BattleAction]:
        """Action IDでActionを取得"""
        return self._actions.get(action_id)
    
    def find_by_ids(self, action_ids: List[int]) -> List[BattleAction]:
        """複数のAction IDでActionを取得"""
        result = []
        for action_id in action_ids:
            action = self._actions.get(action_id)
            if action is not None:
                result.append(action)
        return result
    
    def get_all_actions(self) -> List[BattleAction]:
        """全てのActionを取得"""
        return list(self._actions.values())
    
    def get_basic_actions(self) -> List[BattleAction]:
        """基本Actionを取得（全プレイヤーが最初から使えるAction）"""
        result = []
        for action_id in self._basic_action_ids:
            action = self._actions.get(action_id)
            if action is not None:
                result.append(action)
        return result
    
    def get_actions_by_type(self, action_type: ActionType) -> List[BattleAction]:
        """Actionタイプでフィルタリング"""
        return [action for action in self._actions.values() 
                if action.action_type == action_type]
    
    def get_evolution_chain(self, action_id: int) -> List[int]:
        """進化チェーンを取得（基本形から最終進化まで）"""
        return self._evolution_chains.get(action_id, [action_id])
    
    def get_action_cost(self, action_id: int) -> int:
        """アクションのキャパシティコストを取得"""
        return self._action_costs.get(action_id, 1)  # デフォルトは1
    
    def get_learnable_actions(self, level: int, role: Role) -> List[int]:
        """指定されたレベルと職業で習得可能なアクションIDを取得"""
        # レベル以下の全ての習得可能アクションを取得
        result = set()
        for (req_level, req_role), action_ids in self._learnable_actions.items():
            if req_level <= level and req_role == role:
                result.update(action_ids)
        return list(result)
    
    def get_evolution_requirements(self, action_id: int) -> Optional[tuple[int, int]]:
        """進化に必要な条件を取得（経験値、レベル）。進化できない場合はNone"""
        return self._evolution_requirements.get(action_id)
    
    def get_evolved_action_id(self, action_id: int) -> Optional[int]:
        """進化後のアクションIDを取得。進化できない場合はNone"""
        chain = self._evolution_chains.get(action_id, [])
        if len(chain) <= 1:
            return None
        
        # チェーン内で現在のアクションの次を探す
        try:
            current_index = chain.index(action_id)
            if current_index < len(chain) - 1:
                return chain[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def is_basic_action(self, action_id: int) -> bool:
        """基本アクション（全員が最初から使える）かどうか"""
        return action_id in self._basic_action_ids
    
    def add_action(self, action: BattleAction) -> None:
        """アクションを追加（テスト用）"""
        self._actions[action.action_id] = action
    
    def set_action_cost(self, action_id: int, cost: int) -> None:
        """アクションコストを設定（テスト用）"""
        self._action_costs[action_id] = cost
    
    def add_evolution_chain(self, action_ids: List[int]) -> None:
        """進化チェーンを追加（テスト用）"""
        for action_id in action_ids:
            self._evolution_chains[action_id] = action_ids
    
    def set_evolution_requirement(self, action_id: int, required_exp: int, required_level: int) -> None:
        """進化要件を設定（テスト用）"""
        self._evolution_requirements[action_id] = (required_exp, required_level)
    
    def add_learnable_action(self, level: int, role: Role, action_id: int) -> None:
        """習得可能アクションを追加（テスト用）"""
        key = (level, role)
        if key not in self._learnable_actions:
            self._learnable_actions[key] = []
        if action_id not in self._learnable_actions[key]:
            self._learnable_actions[key].append(action_id)