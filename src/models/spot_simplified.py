from typing import Optional, List, Dict, Set
from .item import Item
from .action import Exploration, Interaction
from .interactable import InteractableObject
from .spot_action import SpotAction, ActionResult, ActionWarning, ActionPermissionChecker, ExplorationSpotAction


class SimplifiedSpot:
    """状態管理を簡素化したSpotクラス"""
    
    def __init__(self, spot_id: str, name: str, description: str):
        self.spot_id = spot_id
        self.name = name
        self.description = description
        
        # 基本的な状態のみ管理
        self.items: List[Item] = []
        self.interactables: Dict[str, InteractableObject] = {}
        self.monsters: Dict[str, 'Monster'] = {}
        self.hidden_monsters: Dict[str, 'Monster'] = {}
        
        # SpotActionシステム
        self.spot_actions: Dict[str, SpotAction] = {}
        self.permission_checker: ActionPermissionChecker = ActionPermissionChecker(spot_id)
        
        # 移動情報はMovementGraphに委譲
        self.movement_graph = None
        
        # デフォルト行動の初期化
        self._initialize_default_actions()
    
    def _initialize_default_actions(self):
        """デフォルトの行動を初期化"""
        exploration_action = ExplorationSpotAction("exploration_general", "general")
        self.add_spot_action(exploration_action)
    
    def set_movement_graph(self, movement_graph):
        """MovementGraphを設定"""
        self.movement_graph = movement_graph
    
    def get_available_movements(self, agent=None):
        """MovementGraphから移動可能先を取得"""
        if not self.movement_graph:
            return []
        return self.movement_graph.get_available_movements(self.spot_id, agent)
    
    # === アイテム管理 ===
    
    def add_item(self, item: Item):
        """アイテムを追加"""
        self.items.append(item)
    
    def remove_item(self, item: Item):
        """アイテムを削除"""
        if item in self.items:
            self.items.remove(item)
    
    def get_items(self) -> List[Item]:
        """アイテムリストを取得"""
        return self.items.copy()
    
    def get_item_by_id(self, item_id: str) -> Optional[Item]:
        """アイテムをIDで取得"""
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None
    
    # === Interactable管理 ===
    
    def add_interactable(self, interactable: InteractableObject):
        """相互作用可能オブジェクトを追加"""
        self.interactables[interactable.object_id] = interactable
    
    def remove_interactable(self, object_id: str):
        """相互作用可能オブジェクトを削除"""
        if object_id in self.interactables:
            del self.interactables[object_id]
    
    def get_interactable_by_id(self, object_id: str) -> Optional[InteractableObject]:
        """IDで相互作用可能オブジェクトを取得"""
        return self.interactables.get(object_id)
    
    def get_all_interactables(self) -> List[InteractableObject]:
        """全ての相互作用可能オブジェクトを取得"""
        return list(self.interactables.values())
    
    # === モンスター管理 ===
    
    def add_monster(self, monster: 'Monster'):
        """モンスターを追加"""
        from .monster import MonsterType
        monster.set_current_spot(self.spot_id)
        
        if monster.monster_type == MonsterType.HIDDEN:
            self.hidden_monsters[monster.monster_id] = monster
        else:
            self.monsters[monster.monster_id] = monster
    
    def remove_monster(self, monster_id: str):
        """モンスターを削除"""
        if monster_id in self.monsters:
            del self.monsters[monster_id]
        if monster_id in self.hidden_monsters:
            del self.hidden_monsters[monster_id]
    
    def get_visible_monsters(self) -> List['Monster']:
        """見えているモンスターのリストを取得"""
        return list(self.monsters.values())
    
    def get_all_monsters(self) -> List['Monster']:
        """すべてのモンスターを取得"""
        all_monsters = list(self.monsters.values())
        all_monsters.extend(self.hidden_monsters.values())
        return all_monsters
    
    def reveal_hidden_monster(self, monster_id: str) -> bool:
        """隠れているモンスターを発見"""
        if monster_id in self.hidden_monsters:
            monster = self.hidden_monsters[monster_id]
            del self.hidden_monsters[monster_id]
            self.monsters[monster_id] = monster
            return True
        return False
    
    # === SpotAction管理 ===
    
    def add_spot_action(self, action: SpotAction):
        """Spot固有の行動を追加"""
        self.spot_actions[action.action_id] = action
    
    def remove_spot_action(self, action_id: str):
        """Spot固有の行動を削除"""
        if action_id in self.spot_actions:
            del self.spot_actions[action_id]
    
    def get_available_spot_actions(self, agent, world=None) -> List[Dict]:
        """エージェントが実行可能な行動一覧を取得"""
        available_actions = []
        
        # 移動行動をMovementGraphから取得
        for movement in self.get_available_movements(agent):
            from .spot_action import MovementSpotAction
            movement_action = MovementSpotAction(
                action_id=f"movement_{movement.direction}",
                direction=movement.direction,
                target_spot_id=movement.target_spot_id
            )
            warnings = movement_action.can_execute(agent, self, world)
            available_actions.append({
                "action": movement_action,
                "warnings": warnings
            })
        
        # 登録済みのSpot行動を追加
        for action in self.spot_actions.values():
            warnings = action.can_execute(agent, self, world)
            available_actions.append({
                "action": action,
                "warnings": warnings
            })
        
        return available_actions
    
    def execute_spot_action(self, action_id: str, agent, world=None) -> ActionResult:
        """Spot行動を実行"""
        # 移動行動の場合
        if action_id.startswith("movement_"):
            direction = action_id.replace("movement_", "")
            for movement in self.get_available_movements(agent):
                if movement.direction == direction:
                    from .spot_action import MovementSpotAction
                    movement_action = MovementSpotAction(
                        action_id=action_id,
                        direction=movement.direction,
                        target_spot_id=movement.target_spot_id
                    )
                    return movement_action.execute(agent, self, world)
            
            return ActionResult(
                success=False,
                message=f"移動行動 {direction} が見つかりません",
                warnings=[],
                state_changes={}
            )
        
        # 登録済みSpot行動の場合
        action = self.spot_actions.get(action_id)
        if not action:
            return ActionResult(
                success=False,
                message=f"行動 {action_id} が見つかりません",
                warnings=[],
                state_changes={}
            )
        
        return action.execute(agent, self, world)
    
    # === 権限管理 ===
    
    def set_role_permission(self, role, permission):
        """役職に対する権限を設定"""
        self.permission_checker.set_role_permission(role, permission)
    
    def set_agent_permission(self, agent_id: str, permission):
        """特定エージェントの権限を設定"""
        self.permission_checker.set_agent_permission(agent_id, permission)
    
    # === ユーティリティメソッド ===
    
    def __str__(self):
        return f"SimplifiedSpot(spot_id={self.spot_id}, name={self.name})"
    
    def __repr__(self):
        return f"SimplifiedSpot(spot_id={self.spot_id}, name={self.name})" 