from typing import Optional, List, Dict, Set
from .item import Item
from .action import Movement, Exploration, Interaction
from .interactable import InteractableObject
from .spot_action import SpotAction, ActionResult, ActionWarning, ActionPermissionChecker, MovementSpotAction, ExplorationSpotAction


class Spot:
    def __init__(self, spot_id: str, name: str, description: str, parent_spot_id: Optional[str] = None):
        self.spot_id = spot_id
        self.name = name
        self.description = description
        self.parent_spot_id = parent_spot_id
        self.items: List[Item] = []
        
        # Spot内で可能な行動を管理
        self.available_movements: List[Movement] = []
        self.available_explorations: List[Exploration] = []
        
        # 動的に追加される移動（ドアを開けた時など）
        self.dynamic_movements: List[Movement] = []
        
        # 相互作用可能オブジェクトの管理
        self.interactables: Dict[str, InteractableObject] = {}
        
        # モンスター管理
        self.monsters: Dict[str, 'Monster'] = {}  # monster_id -> Monster
        self.hidden_monsters: Dict[str, 'Monster'] = {}  # 隠れているモンスター
        
        # 階層管理用
        self.child_spots: Set[str] = set()  # 子スポットのID一覧
        self.entry_points: Dict[str, str] = {}  # 入口名 -> そこに入った時の最初のspot_id
        self.exit_to_parent: Optional[str] = None  # 親スポットに戻る時の接続先spot_id
        self.is_entrance: bool = False  # このスポットが親の入口かどうか
        self.entrance_name: Optional[str] = None  # 入口の名前（例：「正面玄関」「裏口」）
        
        # === 新SpotActionシステム ===
        self.spot_actions: Dict[str, SpotAction] = {}  # action_id -> SpotAction
        self.permission_checker: ActionPermissionChecker = ActionPermissionChecker(spot_id)
        
        # 既存システムからの自動移行（移動・探索）
        self._initialize_default_actions()

    def _initialize_default_actions(self):
        """デフォルトの行動（移動・探索）をSpotActionとして初期化"""
        # 基本探索行動を追加
        exploration_action = ExplorationSpotAction("exploration_general", "general")
        self.add_spot_action(exploration_action)

    # === SpotActionシステム関連メソッド ===
    
    def add_spot_action(self, action: SpotAction):
        """Spot固有の行動を追加"""
        self.spot_actions[action.action_id] = action
    
    def remove_spot_action(self, action_id: str):
        """Spot固有の行動を削除"""
        if action_id in self.spot_actions:
            del self.spot_actions[action_id]
    
    def get_spot_action(self, action_id: str) -> Optional[SpotAction]:
        """IDでSpot行動を取得"""
        return self.spot_actions.get(action_id)
    
    def get_available_spot_actions(self, agent, world=None) -> List[Dict]:
        """
        エージェントが実行可能な行動一覧を取得
        
        Returns:
            List of {"action": SpotAction, "warnings": List[ActionWarning]}
        """
        available_actions = []
        
        # 移動行動を動的に生成
        for movement in self.get_available_movements():
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
            for movement in self.get_available_movements():
                if movement.direction == direction:
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
    
    def execute_action(self, action, agent, world=None):
        """
        旧Actionシステムとの統一インターフェース
        旧形式のActionオブジェクトを受け取り、適切な処理に振り分ける
        """
        from .action import Movement, Exploration, Interaction
        
        # Movement行動の場合
        if isinstance(action, Movement):
            movement_action = MovementSpotAction(
                action_id=f"movement_{action.direction}",
                direction=action.direction,
                target_spot_id=action.target_spot_id
            )
            result = movement_action.execute(agent, self, world)
            
            # 旧システム互換のため、エージェントの位置を直接更新
            if result.success and world:
                agent.set_current_spot_id(action.target_spot_id)
                
            return result
        
        # Exploration行動の場合
        elif isinstance(action, Exploration):
            exploration_action = ExplorationSpotAction("exploration_custom", "custom")
            exploration_action.custom_exploration = action  # カスタム探索を設定
            result = exploration_action.execute(agent, self, world)
            
            # 旧システム互換のため、直接効果を適用
            if result.success:
                if action.item_id:
                    item = self.get_item_by_id(action.item_id)
                    if item:
                        self.remove_item(item)
                        agent.add_item(item)
                        
                if action.discovered_info:
                    agent.add_discovered_info(action.discovered_info)
                    
                if action.experience_points:
                    agent.add_experience_points(action.experience_points)
                    
                if action.money:
                    agent.add_money(action.money)
                    
            return result
        
        # Interaction行動の場合
        elif isinstance(action, Interaction):
            return self._execute_interaction(action, agent, world)
        
        # Job関連行動をSpotActionに変換
        elif self._is_job_action(action):
            return self._execute_job_action(action, agent, world)
        
        # その他の行動（未実装）はWorldに委譲（段階的移行）
        else:
            if world:
                # 旧システムのメソッドを直接呼び出し
                return self._delegate_to_world(action, agent, world)
            else:
                from .spot_action import ActionResult
                return ActionResult(
                    success=False,
                    message=f"未実装の行動タイプ: {type(action).__name__}",
                    warnings=[],
                    state_changes={}
                )
    
    def _is_job_action(self, action):
        """Job関連行動かどうかを判定"""
        from .action import (CraftItem, EnhanceItem, LearnRecipe, 
                            SellItem, BuyItem, ProvideService, SetupShop, PriceNegotiation,
                            ProvideLodging, ProvideDance, ProvidePrayer,
                            StartBattle, JoinBattle, AttackMonster, DefendBattle, EscapeBattle)
        return isinstance(action, (CraftItem, EnhanceItem, LearnRecipe,
                                  SellItem, BuyItem, ProvideService, SetupShop, PriceNegotiation,
                                  ProvideLodging, ProvideDance, ProvidePrayer,
                                  StartBattle, JoinBattle, AttackMonster, DefendBattle, EscapeBattle))
    
    def _execute_job_action(self, action, agent, world):
        """Job関連行動をSpotActionに変換して実行"""
        from .action import (CraftItem, EnhanceItem, LearnRecipe, 
                            SellItem, BuyItem, ProvideService, SetupShop, PriceNegotiation,
                            ProvideLodging, ProvideDance, ProvidePrayer,
                            StartBattle, JoinBattle, AttackMonster, DefendBattle, EscapeBattle)
        from .spot_action import (ItemCraftingSpotAction, ItemEnhancementSpotAction, 
                                 TradeSpotAction, ServiceProvisionSpotAction, 
                                 BattleInitiationSpotAction, BattleActionSpotAction, ActionResult)
        
        if isinstance(action, CraftItem):
            # CraftItemをItemCraftingSpotActionに変換
            spot_action = ItemCraftingSpotAction(action.recipe_id, action.quantity)
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, EnhanceItem):
            # EnhanceItemをItemEnhancementSpotActionに変換
            spot_action = ItemEnhancementSpotAction(action.item_id, action.enhancement_materials)
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, SellItem):
            # SellItemをTradeSpotActionに変換
            spot_action = TradeSpotAction(
                "sell", action.item_id, action.quantity, 
                action.price_per_item, action.customer_agent_id
            )
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, BuyItem):
            # BuyItemをTradeSpotActionに変換
            spot_action = TradeSpotAction(
                "buy", action.item_id, action.quantity,
                action.price_per_item, action.customer_agent_id
            )
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, ProvideService):
            # ProvideServiceをServiceProvisionSpotActionに変換
            spot_action = ServiceProvisionSpotAction(
                action.service_id, action.target_agent_id, action.custom_price
            )
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, StartBattle):
            # StartBattleをBattleInitiationSpotActionに変換
            spot_action = BattleInitiationSpotAction("start", action.monster_id)
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, JoinBattle):
            # JoinBattleをBattleInitiationSpotActionに変換
            spot_action = BattleInitiationSpotAction("join", battle_id=action.battle_id)
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, AttackMonster):
            # AttackMonsterをBattleActionSpotActionに変換
            spot_action = BattleActionSpotAction("attack", action.monster_id)
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, DefendBattle):
            # DefendBattleをBattleActionSpotActionに変換
            spot_action = BattleActionSpotAction("defend")
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, EscapeBattle):
            # EscapeBattleをBattleActionSpotActionに変換
            spot_action = BattleActionSpotAction("escape")
            return spot_action.execute(agent, self, world)
            
        elif isinstance(action, (LearnRecipe, SetupShop, PriceNegotiation, 
                                ProvideLodging, ProvideDance, ProvidePrayer)):
            # まだSpotAction化していない行動は暫定的に旧システムで処理
            return self._delegate_to_world(action, agent, world)
            
        else:
            return ActionResult(
                success=False,
                message=f"未実装のJob行動: {type(action).__name__}",
                warnings=[],
                state_changes={}
            )
    
    def _delegate_to_world(self, action, agent, world):
        """World固有の処理に委譲（暫定的な実装）"""
        from .spot_action import ActionResult
        try:
            # Worldの旧システムメソッドを呼び出し
            result = world._execute_legacy_action(agent.agent_id, action)
            
            # 結果をActionResultに変換
            if isinstance(result, dict):
                return ActionResult(
                    success=result.get("success", True),
                    message=result.get("message", "行動を実行しました"),
                    warnings=[],
                    state_changes={},
                    additional_data={"original_result": result}
                )
            elif isinstance(result, str):
                # 戦闘IDなど特別な戻り値の場合
                return ActionResult(
                    success=True,
                    message=f"{action.description} を実行しました",
                    warnings=[],
                    state_changes={},
                    additional_data={"return_value": result}
                )
            else:
                return ActionResult(
                    success=True,
                    message=f"{action.description} を実行しました",
                    warnings=[],
                    state_changes={},
                    additional_data={"original_result": result}
                )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"行動の実行中にエラーが発生しました: {str(e)}",
                warnings=[],
                state_changes={}
            )
    
    def _execute_interaction(self, interaction, agent, world):
        """相互作用行動を実行（旧システムからの移行用）"""
        try:
            interactable = self.get_interactable_by_id(interaction.object_id)
            if not interactable:
                return ActionResult(
                    success=False,
                    message=f"オブジェクト {interaction.object_id} が見つかりません",
                    warnings=[],
                    state_changes={}
                )
            
            if not interactable.can_interact(agent, interaction.interaction_type):
                if interaction.required_item_id and not agent.has_item(interaction.required_item_id):
                    return ActionResult(
                        success=False,
                        message=f"アイテム '{interaction.required_item_id}' が必要です",
                        warnings=[],
                        state_changes={}
                    )
                else:
                    return ActionResult(
                        success=False,
                        message=f"この相互作用は実行できません: {interaction.description}",
                        warnings=[],
                        state_changes={}
                    )
            
            # オブジェクトの状態変更
            for key, value in interaction.state_changes.items():
                interactable.set_state(key, value)
            
            # 報酬の付与
            reward = interaction.reward
            for item_id in reward.items:
                if hasattr(interactable, 'items'):
                    for item in interactable.items[:]:
                        if item.item_id == item_id:
                            interactable.items.remove(item)
                            agent.add_item(item)
                            break
                else:
                    item = self.get_item_by_id(item_id)
                    if item:
                        self.remove_item(item)
                        agent.add_item(item)
            
            if reward.money > 0:
                agent.add_money(reward.money)
            
            if reward.experience > 0:
                agent.add_experience_points(reward.experience)
            
            for info in reward.information:
                agent.add_discovered_info(info)
            
            # ドアのOPEN処理時の特別な処理
            from .interactable import Door
            from .action import InteractionType
            if (isinstance(interactable, Door) and 
                interaction.interaction_type == InteractionType.OPEN):
                # ドアを開いた後、双方向の移動を追加
                self._add_bidirectional_door_movement(interactable, world)
            
            return ActionResult(
                success=True,
                message=f"{interaction.description} を実行しました",
                warnings=[],
                state_changes=interaction.state_changes
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"相互作用の実行中にエラーが発生しました: {str(e)}",
                warnings=[],
                state_changes={}
            )
    
    def _add_bidirectional_door_movement(self, door, world):
        """ドア開放時に双方向の移動を追加"""
        from .action import Movement
        
        # 現在のSpotから目標Spotへの移動
        forward_movement = door.creates_movement_when_opened()
        if forward_movement:
            self.add_dynamic_movement(forward_movement)
        
        # 目標Spotから現在のSpotへの戻り移動
        if world:
            target_spot = world.get_spot(door.target_spot_id)
            backward_movement = Movement(
                description=f"{door.name}を通って戻る",
                direction=f"{door.name}を通って戻る", 
                target_spot_id=self.spot_id
            )
            target_spot.add_dynamic_movement(backward_movement)
    
    def set_role_permission(self, role, permission):
        """役職に対する権限を設定"""
        self.permission_checker.set_role_permission(role, permission)
    
    def set_agent_permission(self, agent_id: str, permission):
        """特定エージェントの権限を設定"""
        self.permission_checker.set_agent_permission(agent_id, permission)

    # === 既存メソッドはそのまま維持 ===

    def __str__(self):
        return f"Spot(spot_id={self.spot_id}, name={self.name}, description={self.description}, parent_spot_id={self.parent_spot_id})"
    
    def __repr__(self):
        return f"Spot(spot_id={self.spot_id}, name={self.name}, description={self.description}, parent_spot_id={self.parent_spot_id})"
    
    def get_spot_id(self) -> str:
        """スポットIDを取得"""
        return self.spot_id
    
    def get_name(self) -> str:
        """スポット名を取得"""
        return self.name
    
    def get_description(self) -> str:
        """スポットの説明を取得"""
        return self.description
    
    def get_parent_spot_id(self) -> Optional[str]:
        """親スポットIDを取得"""
        return self.parent_spot_id

    def add_child_spot(self, child_spot_id: str):
        """子スポットを追加"""
        self.child_spots.add(child_spot_id)
    
    def remove_child_spot(self, child_spot_id: str):
        """子スポットを削除"""
        self.child_spots.discard(child_spot_id)
    
    def add_entry_point(self, entrance_name: str, first_spot_id: str):
        """入口を追加（例：「正面玄関」-> 「学校_1階廊下」）"""
        self.entry_points[entrance_name] = first_spot_id
    
    def set_exit_to_parent(self, parent_spot_id: str):
        """親スポットに戻る時の接続先を設定"""
        self.exit_to_parent = parent_spot_id
    
    def set_as_entrance(self, entrance_name: str):
        """このスポットを親の入口として設定"""
        self.is_entrance = True
        self.entrance_name = entrance_name
    
    def get_child_spots(self) -> Set[str]:
        """子スポットを取得"""
        return self.child_spots.copy()
    
    def get_entry_points(self) -> Dict[str, str]:
        """入口を取得"""
        return self.entry_points.copy()
    
    def can_exit_to_parent(self) -> bool:
        """親スポットに出ることができるかどうか"""
        return self.exit_to_parent is not None
    
    def is_entrance_spot(self) -> bool:
        """このスポットが入口かどうか"""
        return self.is_entrance
    
    def get_entrance_name(self) -> Optional[str]:
        """入口の名前を取得"""
        return self.entrance_name

    def add_item(self, item: Item):
        """アイテムを追加"""
        self.items.append(item)
    
    def remove_item(self, item: Item):
        """アイテムを削除"""
        self.items.remove(item)
    
    def get_items(self) -> List[Item]:
        """アイテムリストを取得"""
        return self.items
    
    def get_item_by_id(self, item_id: str) -> Optional[Item]:
        """アイテムをIDで取得"""
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def add_movement(self, movement: Movement):
        """可能な移動行動を追加"""
        self.available_movements.append(movement)

    def add_dynamic_movement(self, movement: Movement):
        """動的に移動先を追加（重複チェック付き）"""
        # 重複チェック：同じtarget_spot_idとdirectionの組み合わせは追加しない
        for existing_movement in self.dynamic_movements:
            if (existing_movement.target_spot_id == movement.target_spot_id and 
                existing_movement.direction == movement.direction):
                return  # 既に存在する場合は追加しない
        
        self.dynamic_movements.append(movement)
    
    def remove_dynamic_movement(self, target_spot_id: str, direction: str):
        """動的移動を削除"""
        self.dynamic_movements = [
            movement for movement in self.dynamic_movements
            if not (movement.target_spot_id == target_spot_id and movement.direction == direction)
        ]
    
    def get_dynamic_movements(self) -> List[Movement]:
        """動的移動のリストを取得"""
        return self.dynamic_movements.copy()

    def get_available_movements(self) -> List[Movement]:
        """可能な移動行動を全て取得（静的 + 動的 + 階層移動）"""
        movements = self.available_movements.copy()
        
        # 動的に追加された移動を追加
        movements.extend(self.dynamic_movements)
        
        # 親スポットに戻る移動を追加
        if self.exit_to_parent:
            movements.append(Movement(
                description="外に出る",
                direction="外に出る",
                target_spot_id=self.exit_to_parent
            ))
        
        # 子スポットへの入口移動を追加
        for entrance_name, target_spot_id in self.entry_points.items():
            movements.append(Movement(
                description=f"{entrance_name}に入る",
                direction=f"{entrance_name}に入る",
                target_spot_id=target_spot_id
            ))
        
        return movements
    
    def add_exploration(self, exploration: Exploration):
        """可能な探索行動を追加"""
        self.available_explorations.append(exploration)
    
    def get_available_explorations(self) -> List[Exploration]:
        """可能な探索行動を全て取得"""
        return self.available_explorations
    
    # === Interactableオブジェクト管理 ===
    
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
    
    # === モンスター管理 ===
    
    def add_monster(self, monster: 'Monster'):
        """モンスターを追加"""
        from .monster import MonsterType
        monster.set_current_spot(self.spot_id)
        
        if monster.monster_type == MonsterType.HIDDEN:
            # 隠れているモンスターは探索で発見されるまで見えない
            self.hidden_monsters[monster.monster_id] = monster
        else:
            # 通常のモンスター（見える状態）
            self.monsters[monster.monster_id] = monster
    
    def remove_monster(self, monster_id: str):
        """モンスターを削除（倒された場合など）"""
        if monster_id in self.monsters:
            del self.monsters[monster_id]
        if monster_id in self.hidden_monsters:
            del self.hidden_monsters[monster_id]
    
    def get_monster_by_id(self, monster_id: str) -> Optional['Monster']:
        """IDでモンスターを取得"""
        if monster_id in self.monsters:
            return self.monsters[monster_id]
        if monster_id in self.hidden_monsters:
            return self.hidden_monsters[monster_id]
        return None
    
    def get_visible_monsters(self) -> List['Monster']:
        """見えているモンスターのリストを取得"""
        return list(self.monsters.values())
    
    def get_all_monsters(self) -> List['Monster']:
        """すべてのモンスター（隠れているものも含む）を取得"""
        all_monsters = list(self.monsters.values())
        all_monsters.extend(self.hidden_monsters.values())
        return all_monsters
    
    def reveal_hidden_monster(self, monster_id: str) -> bool:
        """隠れているモンスターを発見する（探索時に使用）"""
        if monster_id in self.hidden_monsters:
            monster = self.hidden_monsters[monster_id]
            del self.hidden_monsters[monster_id]
            self.monsters[monster_id] = monster
            return True
        return False
    
    def has_aggressive_monsters(self) -> bool:
        """攻撃的なモンスターがいるかどうか"""
        from .monster import MonsterType
        for monster in self.monsters.values():
            if monster.monster_type == MonsterType.AGGRESSIVE:
                return True
        return False
    
    def get_aggressive_monsters(self) -> List['Monster']:
        """攻撃的なモンスターのリストを取得"""
        from .monster import MonsterType
        return [monster for monster in self.monsters.values() 
                if monster.monster_type == MonsterType.AGGRESSIVE]
    
    def get_all_interactables(self) -> List[InteractableObject]:
        """全ての相互作用可能オブジェクトを取得"""
        return list(self.interactables.values())
    
    def get_available_interactions(self) -> List[Interaction]:
        """このSpotで利用可能な全ての相互作用を取得"""
        all_interactions = []
        for interactable in self.interactables.values():
            all_interactions.extend(interactable.get_available_interactions())
        return all_interactions