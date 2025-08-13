from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod


class Permission(Enum):
    """権限レベル"""
    OWNER = "owner"           # 所有者権限（店主など）
    EMPLOYEE = "employee"     # 従業員権限
    CUSTOMER = "customer"     # 顧客権限（一般的な利用者）
    MEMBER = "member"         # メンバー権限（ギルド会員など）
    GUEST = "guest"           # ゲスト権限（最低限の利用）
    DENIED = "denied"         # アクセス拒否


class Role(Enum):
    """エージェントの役職"""
    # 基本職業
    CITIZEN = "citizen"           # 一般市民
    ADVENTURER = "adventurer"     # 冒険者
    
    # 商業関連
    MERCHANT = "merchant"         # 商人
    SHOP_KEEPER = "shop_keeper"   # 店主
    TRADER = "trader"             # 貿易商
    
    # 職人関連  
    CRAFTSMAN = "craftsman"       # 職人
    BLACKSMITH = "blacksmith"     # 鍛冶師
    ALCHEMIST = "alchemist"       # 錬金術師
    TAILOR = "tailor"             # 仕立て屋
    
    # サービス関連
    INNKEEPER = "innkeeper"       # 宿屋の主人
    DANCER = "dancer"             # 踊り子
    PRIEST = "priest"             # 僧侶
    
    # 一次産業
    FARMER = "farmer"             # 農家
    FISHER = "fisher"             # 漁師
    MINER = "miner"               # 鉱夫
    WOODCUTTER = "woodcutter"     # 木こり


@dataclass
class ActionWarning:
    """行動実行時の警告情報"""
    message: str                  # 警告メッセージ
    warning_type: str            # 警告タイプ（permission, condition, resource など）
    is_blocking: bool = False    # 実行をブロックするかどうか


@dataclass  
class ActionResult:
    """行動実行結果の統一フォーマット"""
    success: bool                           # 実行成功可否
    message: str                           # 結果メッセージ
    warnings: List[ActionWarning]          # 警告リスト
    state_changes: Dict[str, Any]          # 状態変化（エージェント、Spot等）
    items_gained: List[str] = None         # 獲得アイテムID一覧
    items_lost: List[str] = None           # 失ったアイテムID一覧  
    money_change: int = 0                  # 金銭変化
    experience_gained: int = 0             # 経験値獲得
    additional_data: Dict[str, Any] = None # 追加データ（行動固有の情報）
    
    def __post_init__(self):
        if self.items_gained is None:
            self.items_gained = []
        if self.items_lost is None:
            self.items_lost = []
        if self.additional_data is None:
            self.additional_data = {}
        if self.warnings is None:
            self.warnings = []


class ActionPermissionChecker:
    """権限チェック機能を提供するクラス"""
    
    def __init__(self, spot_id: str):
        self.spot_id = spot_id
        # Spot固有の権限設定（役職 -> 権限レベル）
        self.role_permissions: Dict[Role, Permission] = {
            Role.CITIZEN: Permission.CUSTOMER,
            Role.ADVENTURER: Permission.CUSTOMER,
        }
        # 特定エージェントの個別権限設定（agent_id -> 権限レベル）
        self.agent_permissions: Dict[str, Permission] = {}
    
    def set_role_permission(self, role: Role, permission: Permission):
        """役職に対する権限レベルを設定"""
        self.role_permissions[role] = permission
    
    def set_agent_permission(self, agent_id: str, permission: Permission):
        """特定エージェントの権限レベルを設定"""
        self.agent_permissions[agent_id] = permission
    
    def get_agent_permission(self, agent) -> Permission:
        """エージェントの権限レベルを取得"""
        # 個別権限が設定されている場合は優先
        if hasattr(agent, 'agent_id') and agent.agent_id in self.agent_permissions:
            return self.agent_permissions[agent.agent_id]
        
        # 役職による権限を確認
        if hasattr(agent, 'role') and agent.role in self.role_permissions:
            return self.role_permissions[agent.role]
        
        # 既存のJobAgentからの権限マッピング（暫定的対応）
        if hasattr(agent, 'job_type'):
            return self._map_job_to_permission(agent.job_type)
        
        # デフォルトはゲスト権限
        return Permission.GUEST
    
    def _map_job_to_permission(self, job_type) -> Permission:
        """既存JobTypeから権限への暫定マッピング"""
        from ..models.job import JobType
        mapping = {
            JobType.MERCHANT: Permission.EMPLOYEE,    # 商人は従業員権限
            JobType.CRAFTSMAN: Permission.EMPLOYEE,   # 職人は従業員権限  
            JobType.ADVENTURER: Permission.CUSTOMER,  # 冒険者は顧客権限
            JobType.PRODUCER: Permission.EMPLOYEE,    # 生産者は従業員権限
        }
        return mapping.get(job_type, Permission.GUEST)
    
    def check_permission(self, agent, required_permission: Permission) -> bool:
        """エージェントが必要な権限を持っているかチェック"""
        agent_permission = self.get_agent_permission(agent)
        
        # 権限レベルの序列
        permission_levels = {
            Permission.DENIED: 0,
            Permission.GUEST: 1,
            Permission.CUSTOMER: 2,
            Permission.MEMBER: 3,
            Permission.EMPLOYEE: 4,
            Permission.OWNER: 5
        }
        
        agent_level = permission_levels.get(agent_permission, 0)
        required_level = permission_levels.get(required_permission, 5)
        
        return agent_level >= required_level


class SpotAction(ABC):
    """Spot行動の基底クラス"""
    
    def __init__(
        self, 
        action_id: str,
        name: str, 
        description: str,
        required_permission: Permission = Permission.CUSTOMER
    ):
        self.action_id = action_id
        self.name = name
        self.description = description
        self.required_permission = required_permission
    
    @abstractmethod
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        """
        行動実行可能性をチェック
        
        Returns:
            警告リスト（空なら実行可能、blocking警告があれば実行不可）
        """
        pass
    
    @abstractmethod
    def execute(self, agent, spot, world=None) -> ActionResult:
        """
        行動を実行
        
        Returns:
            行動実行結果
        """
        pass
    
    def check_permission(self, agent, permission_checker: ActionPermissionChecker) -> List[ActionWarning]:
        """権限チェック（共通機能）"""
        warnings = []
        
        if not permission_checker.check_permission(agent, self.required_permission):
            agent_permission = permission_checker.get_agent_permission(agent)
            warnings.append(ActionWarning(
                message=f"権限不足: {self.required_permission.value}が必要ですが、{agent_permission.value}権限です",
                warning_type="permission",
                is_blocking=True
            ))
        
        return warnings


# === Job系SpotAction実装 ===

class CraftingSpotAction(SpotAction):
    """クラフト系行動の基底クラス"""
    
    def __init__(self, action_id: str, name: str, description: str, 
                 required_permission: Permission = Permission.CUSTOMER):
        super().__init__(action_id, name, description, required_permission)
    
    def check_crafting_requirements(self, agent, recipe_id: str = None) -> List[ActionWarning]:
        """クラフト要件チェック（共通機能）"""
        warnings = []
        
        # JobAgentかチェック
        from ..models.job import JobAgent
        if not isinstance(agent, JobAgent):
            warnings.append(ActionWarning(
                message="クラフト行動には職業エージェントが必要です",
                warning_type="agent_type",
                is_blocking=True
            ))
            return warnings
        
        # レシピ要件チェック（レシピIDが指定されている場合）
        if recipe_id:
            recipe = agent.get_recipe_by_id(recipe_id)
            if not recipe:
                warnings.append(ActionWarning(
                    message=f"レシピ {recipe_id} を習得していません",
                    warning_type="recipe",
                    is_blocking=True
                ))
            elif not recipe.can_craft(agent):
                missing = recipe.get_missing_materials(agent)
                warnings.append(ActionWarning(
                    message=f"材料不足: {missing}",
                    warning_type="materials",
                    is_blocking=True
                ))
        
        return warnings


class ItemCraftingSpotAction(CraftingSpotAction):
    """アイテム合成SpotAction"""
    
    def __init__(self, recipe_id: str, quantity: int = 1):
        super().__init__(
            action_id=f"craft_{recipe_id}",
            name=f"アイテム合成({recipe_id})",
            description=f"{recipe_id}を{quantity}個合成する",
            required_permission=Permission.CUSTOMER
        )
        self.recipe_id = recipe_id
        self.quantity = quantity
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # クラフト要件チェック
        warnings.extend(self.check_crafting_requirements(agent, self.recipe_id))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        from ..models.job import JobAgent
        
        # 実行可能性チェック
        warnings = self.can_execute(agent, spot, world)
        blocking_warnings = [w for w in warnings if w.is_blocking]
        
        if blocking_warnings:
            return ActionResult(
                success=False,
                message=f"アイテム合成を実行できません: {blocking_warnings[0].message}",
                warnings=warnings,
                state_changes={}
            )
        
        # JobAgentのcraft_itemメソッドを使用
        recipe = agent.get_recipe_by_id(self.recipe_id)
        craft_result = agent.craft_item(recipe, self.quantity)
        
        # 結果をActionResultに変換
        return ActionResult(
            success=craft_result["success"],
            message=f"合成結果: {', '.join(craft_result['messages'])}",
            warnings=warnings,
            state_changes={"consumed_materials": craft_result["consumed_materials"]},
            items_gained=[item.item_id for item in craft_result["created_items"]],
            experience_gained=craft_result["experience_gained"],
            additional_data={"craft_result": craft_result}
        )


class ItemEnhancementSpotAction(CraftingSpotAction):
    """アイテム強化SpotAction"""
    
    def __init__(self, target_item_id: str, enhancement_materials: Dict[str, int]):
        super().__init__(
            action_id=f"enhance_{target_item_id}",
            name=f"アイテム強化({target_item_id})",
            description=f"{target_item_id}を強化する",
            required_permission=Permission.CUSTOMER
        )
        self.target_item_id = target_item_id
        self.enhancement_materials = enhancement_materials
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 基本要件チェック
        warnings.extend(self.check_crafting_requirements(agent))
        
        # 対象アイテムチェック
        if not agent.has_item(self.target_item_id):
            warnings.append(ActionWarning(
                message=f"強化対象アイテム {self.target_item_id} を所持していません",
                warning_type="item",
                is_blocking=True
            ))
        
        # 強化材料チェック
        for material_id, count in self.enhancement_materials.items():
            if agent.get_item_count(material_id) < count:
                warnings.append(ActionWarning(
                    message=f"強化材料 {material_id} が不足（必要: {count}個）",
                    warning_type="materials",
                    is_blocking=True
                ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        # 実行可能性チェック
        warnings = self.can_execute(agent, spot, world)
        blocking_warnings = [w for w in warnings if w.is_blocking]
        
        if blocking_warnings:
            return ActionResult(
                success=False,
                message=f"アイテム強化を実行できません: {blocking_warnings[0].message}",
                warnings=warnings,
                state_changes={}
            )
        
        # JobAgentのenhance_itemメソッドを使用
        enhance_result = agent.enhance_item(self.target_item_id, self.enhancement_materials)
        
        # 結果をActionResultに変換
        return ActionResult(
            success=enhance_result["success"],
            message=f"強化結果: {', '.join(enhance_result['messages'])}",
            warnings=warnings,
            state_changes={"consumed_materials": enhance_result["consumed_materials"]},
            experience_gained=enhance_result["experience_gained"],
            additional_data={"enhance_result": enhance_result}
        )


class TradeSpotAction(SpotAction):
    """商取引SpotAction（売買統合）"""
    
    def __init__(self, trade_type: str, item_id: str, quantity: int, 
                 price_per_item: int, counterpart_agent_id: str):
        action_id = f"{trade_type}_{item_id}_{counterpart_agent_id}"
        name = f"アイテム{'売却' if trade_type == 'sell' else '購入'}"
        description = f"{item_id}を{quantity}個{'売却' if trade_type == 'sell' else '購入'}する"
        
        super().__init__(action_id, name, description, Permission.CUSTOMER)
        self.trade_type = trade_type  # "sell" or "buy"
        self.item_id = item_id
        self.quantity = quantity
        self.price_per_item = price_per_item
        self.counterpart_agent_id = counterpart_agent_id
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # JobAgentかチェック
        from ..models.job import JobAgent
        if not isinstance(agent, JobAgent):
            warnings.append(ActionWarning(
                message="取引行動には職業エージェントが必要です",
                warning_type="agent_type",
                is_blocking=True
            ))
            return warnings
        
        # 取引相手の存在チェック
        if world and self.counterpart_agent_id not in world.agents:
            warnings.append(ActionWarning(
                message=f"取引相手 {self.counterpart_agent_id} が見つかりません",
                warning_type="counterpart",
                is_blocking=True
            ))
        
        # 売却の場合：アイテム所持チェック
        if self.trade_type == "sell":
            if agent.get_item_count(self.item_id) < self.quantity:
                warnings.append(ActionWarning(
                    message=f"アイテム {self.item_id} が不足（必要: {self.quantity}個）",
                    warning_type="item",
                    is_blocking=True
                ))
        
        # 購入の場合：資金チェック
        elif self.trade_type == "buy":
            total_cost = self.price_per_item * self.quantity
            if agent.get_money() < total_cost:
                warnings.append(ActionWarning(
                    message=f"資金不足（必要: {total_cost}ゴールド、所持: {agent.get_money()}ゴールド）",
                    warning_type="money",
                    is_blocking=True
                ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        # 実行可能性チェック
        warnings = self.can_execute(agent, spot, world)
        blocking_warnings = [w for w in warnings if w.is_blocking]
        
        if blocking_warnings:
            return ActionResult(
                success=False,
                message=f"取引を実行できません: {blocking_warnings[0].message}",
                warnings=warnings,
                state_changes={}
            )
        
        # 取引実行
        if self.trade_type == "sell":
            result = agent.sell_item_to_customer(
                self.counterpart_agent_id, self.item_id, 
                self.quantity, self.price_per_item
            )
        else:  # "buy"
            result = agent.buy_item_from_customer(
                self.counterpart_agent_id, self.item_id,
                self.quantity, self.price_per_item
            )
        
        # 結果をActionResultに変換
        total_price = self.price_per_item * self.quantity
        return ActionResult(
            success=result["success"],
            message=f"取引結果: {', '.join(result['messages'])}",
            warnings=warnings,
            state_changes={},
            items_gained=[self.item_id] * self.quantity if self.trade_type == "buy" else [],
            items_lost=[self.item_id] * self.quantity if self.trade_type == "sell" else [],
            money_change=total_price if self.trade_type == "sell" else -total_price,
            experience_gained=result.get("experience_gained", 0),
            additional_data={"trade_result": result}
        )


class ServiceProvisionSpotAction(SpotAction):
    """サービス提供SpotAction"""
    
    def __init__(self, service_id: str, target_agent_id: str, 
                 custom_price: Optional[int] = None):
        super().__init__(
            action_id=f"service_{service_id}_{target_agent_id}",
            name=f"サービス提供({service_id})",
            description=f"{target_agent_id}にサービス{service_id}を提供する",
            required_permission=Permission.EMPLOYEE
        )
        self.service_id = service_id
        self.target_agent_id = target_agent_id
        self.custom_price = custom_price
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # JobAgentかチェック
        from ..models.job import JobAgent
        if not isinstance(agent, JobAgent):
            warnings.append(ActionWarning(
                message="サービス提供行動には職業エージェントが必要です",
                warning_type="agent_type",
                is_blocking=True
            ))
            return warnings
        
        # サービス提供可能かチェック
        service = agent.get_service_by_id(self.service_id)
        if not service:
            warnings.append(ActionWarning(
                message=f"サービス {self.service_id} を提供できません",
                warning_type="service",
                is_blocking=True
            ))
        elif not service.can_provide(agent):
            warnings.append(ActionWarning(
                message=f"サービス {self.service_id} の提供条件を満たしていません",
                warning_type="requirements",
                is_blocking=True
            ))
        
        # 対象エージェントの存在チェック
        if world and self.target_agent_id not in world.agents:
            warnings.append(ActionWarning(
                message=f"対象エージェント {self.target_agent_id} が見つかりません",
                warning_type="target",
                is_blocking=True
            ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        # 実行可能性チェック
        warnings = self.can_execute(agent, spot, world)
        blocking_warnings = [w for w in warnings if w.is_blocking]
        
        if blocking_warnings:
            return ActionResult(
                success=False,
                message=f"サービス提供を実行できません: {blocking_warnings[0].message}",
                warnings=warnings,
                state_changes={}
            )
        
        # サービス提供実行
        result = agent.provide_service(
            self.service_id, self.target_agent_id, self.custom_price
        )
        
        # 支払い処理
        if result["success"] and world:
            price = result["price_charged"]
            target_agent = world.get_agent(self.target_agent_id)
            if target_agent.get_money() >= price:
                target_agent.add_money(-price)
                agent.add_money(price)
                result["messages"].append(f"{price}ゴールドが支払われました")
            else:
                result["success"] = False
                result["messages"].append("支払い能力が不足しています")
        
        # 結果をActionResultに変換
        return ActionResult(
            success=result["success"],
            message=f"サービス提供結果: {', '.join(result['messages'])}",
            warnings=warnings,
            state_changes={},
            money_change=result.get("price_charged", 0),
            experience_gained=result.get("experience_gained", 0),
            additional_data={"service_result": result}
        )


class BattleSpotAction(SpotAction):
    """戦闘系行動の基底クラス"""
    
    def __init__(self, action_id: str, name: str, description: str,
                 required_permission: Permission = Permission.CUSTOMER):
        super().__init__(action_id, name, description, required_permission)
    
    def check_battle_requirements(self, agent, spot, world=None) -> List[ActionWarning]:
        """戦闘要件チェック（共通機能）"""
        warnings = []
        
        # エージェントが生存しているかチェック
        if not agent.is_alive():
            warnings.append(ActionWarning(
                message="戦闘不能状態では戦闘行動を実行できません",
                warning_type="agent_state",
                is_blocking=True
            ))
        
        return warnings


class BattleInitiationSpotAction(BattleSpotAction):
    """戦闘開始・参加SpotAction"""
    
    def __init__(self, action_type: str, monster_id: str = None, battle_id: str = None):
        if action_type == "start":
            action_id = f"start_battle_{monster_id}"
            name = "戦闘開始"
            description = f"{monster_id}との戦闘を開始する"
        else:  # "join"
            action_id = f"join_battle_{battle_id}"
            name = "戦闘参加"
            description = f"戦闘{battle_id}に参加する"
        
        super().__init__(action_id, name, description, Permission.CUSTOMER)
        self.action_type = action_type
        self.monster_id = monster_id
        self.battle_id = battle_id
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 戦闘要件チェック
        warnings.extend(self.check_battle_requirements(agent, spot, world))
        
        if self.action_type == "start":
            # モンスター存在チェック
            monster = spot.get_monster_by_id(self.monster_id) if self.monster_id else None
            if not monster:
                warnings.append(ActionWarning(
                    message=f"モンスター {self.monster_id} が見つかりません",
                    warning_type="monster",
                    is_blocking=True
                ))
            elif not monster.is_alive:
                warnings.append(ActionWarning(
                    message=f"{monster.name} は既に倒されています",
                    warning_type="monster_state",
                    is_blocking=True
                ))
        
        elif self.action_type == "join":
            # 戦闘存在チェック
            if world:
                battle = world.battle_manager.get_battle(self.battle_id) if self.battle_id else None
                if not battle:
                    warnings.append(ActionWarning(
                        message=f"戦闘 {self.battle_id} が見つかりません",
                        warning_type="battle",
                        is_blocking=True
                    ))
                elif battle.spot_id != spot.spot_id:
                    warnings.append(ActionWarning(
                        message="同じスポットにいないため戦闘に参加できません",
                        warning_type="location",
                        is_blocking=True
                    ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        # 実行可能性チェック
        warnings = self.can_execute(agent, spot, world)
        blocking_warnings = [w for w in warnings if w.is_blocking]
        
        if blocking_warnings:
            return ActionResult(
                success=False,
                message=f"戦闘行動を実行できません: {blocking_warnings[0].message}",
                warnings=warnings,
                state_changes={}
            )
        
        if self.action_type == "start":
            # 戦闘開始
            monster = spot.get_monster_by_id(self.monster_id)
            battle_id = world.battle_manager.start_battle(spot.spot_id, monster, agent)
            
            # 同じスポットの他のエージェントに通知
            agents_in_spot = world.get_agents_in_spot(spot.spot_id)
            for other_agent in agents_in_spot:
                if other_agent.agent_id != agent.agent_id:
                    notification = f"{agent.name} が {monster.name} との戦闘を開始しました！"
                    other_agent.add_discovered_info(notification)
            
            return ActionResult(
                success=True,
                message=f"戦闘開始: {monster.name}",
                warnings=warnings,
                state_changes={"battle_started": True},
                additional_data={"battle_id": battle_id}
            )
        
        else:  # "join"
            # 戦闘参加
            battle = world.battle_manager.get_battle(self.battle_id)
            battle.add_participant(agent)
            
            return ActionResult(
                success=True,
                message=f"戦闘に参加しました",
                warnings=warnings,
                state_changes={"battle_joined": True},
                additional_data={"battle_id": self.battle_id}
            )


class BattleActionSpotAction(BattleSpotAction):
    """戦闘中の行動SpotAction"""
    
    def __init__(self, battle_action_type: str, target_id: str = None):
        action_id = f"battle_{battle_action_type}"
        if battle_action_type == "attack":
            name = "攻撃"
            description = f"{target_id}を攻撃する"
        elif battle_action_type == "defend":
            name = "防御"
            description = "防御態勢を取る"
        else:  # "escape"
            name = "逃走"
            description = "戦闘から逃走する"
        
        super().__init__(action_id, name, description, Permission.CUSTOMER)
        self.battle_action_type = battle_action_type
        self.target_id = target_id
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 戦闘要件チェック
        warnings.extend(self.check_battle_requirements(agent, spot, world))
        
        # 進行中戦闘チェック
        if world:
            battle = world.battle_manager.get_battle_by_spot(spot.spot_id)
            if not battle:
                warnings.append(ActionWarning(
                    message="現在戦闘中ではありません",
                    warning_type="battle_state",
                    is_blocking=True
                ))
            elif agent.agent_id not in battle.participants:
                warnings.append(ActionWarning(
                    message="この戦闘に参加していません",
                    warning_type="battle_participation",
                    is_blocking=True
                ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        # 実行可能性チェック
        warnings = self.can_execute(agent, spot, world)
        blocking_warnings = [w for w in warnings if w.is_blocking]
        
        if blocking_warnings:
            return ActionResult(
                success=False,
                message=f"戦闘行動を実行できません: {blocking_warnings[0].message}",
                warnings=warnings,
                state_changes={}
            )
        
        # 戦闘行動実行
        battle = world.battle_manager.get_battle_by_spot(spot.spot_id)
        
        # 行動オブジェクトを作成（旧システムとの互換性のため）
        from ..models.action import AttackMonster, DefendBattle, EscapeBattle
        if self.battle_action_type == "attack":
            action = AttackMonster("モンスターを攻撃", self.target_id)
        elif self.battle_action_type == "defend":
            action = DefendBattle("防御")
        else:  # "escape"
            action = EscapeBattle("逃走")
        
        # 戦闘行動を実行
        turn_action = battle.execute_agent_action(agent.agent_id, action)
        battle.advance_turn()
        
        # モンスターのターンの場合は自動実行
        if battle.is_monster_turn() and not battle.is_battle_finished():
            monster_action = battle.execute_monster_turn()
            battle.advance_turn()
        
        # 戦闘終了チェック
        if battle.is_battle_finished():
            result = world.battle_manager.finish_battle(battle.battle_id)
            world._handle_battle_result(result)
            return ActionResult(
                success=True,
                message=f"戦闘終了: {result.victory}",
                warnings=warnings,
                state_changes={"battle_finished": True},
                additional_data={"battle_result": result}
            )
        
        return ActionResult(
            success=True,
            message=f"戦闘継続中: {turn_action.message}",
            warnings=warnings,
            state_changes={"turn_completed": True},
            additional_data={"turn_action": turn_action}
        )


class MovementSpotAction(SpotAction):
    """移動行動のSpotAction実装"""
    
    def __init__(self, action_id: str, direction: str, target_spot_id: str):
        super().__init__(
            action_id=action_id,
            name=f"{direction}に移動", 
            description=f"{direction}方向への移動",
            required_permission=Permission.GUEST
        )
        self.direction = direction
        self.target_spot_id = target_spot_id
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック（Spotの権限設定を使用）
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 移動先の存在チェック
        if world and not world.spots.get(self.target_spot_id):
            warnings.append(ActionWarning(
                message=f"移動先 {self.target_spot_id} が存在しません",
                warning_type="condition",
                is_blocking=True
            ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        warnings = self.can_execute(agent, spot, world)
        
        # ブロッキング警告がある場合は失敗
        if any(w.is_blocking for w in warnings):
            return ActionResult(
                success=False,
                message="移動に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 移動実行
        old_spot_id = agent.get_current_spot_id()
        agent.set_current_spot_id(self.target_spot_id)
        
        return ActionResult(
            success=True,
            message=f"{spot.name}から{self.direction}に移動しました",
            warnings=warnings,
            state_changes={
                "agent_location": {
                    "old_spot_id": old_spot_id,
                    "new_spot_id": self.target_spot_id
                }
            }
        )


class ExplorationSpotAction(SpotAction):
    """探索行動のSpotAction実装"""
    
    def __init__(self, action_id: str, exploration_type: str = "general"):
        super().__init__(
            action_id=action_id,
            name="探索", 
            description=f"{exploration_type}探索を行う",
            required_permission=Permission.GUEST
        )
        self.exploration_type = exploration_type
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック（Spotの権限設定を使用）
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 探索可能なコンテンツの存在チェック
        explorable_content = len(spot.get_items()) + len(spot.get_all_monsters())
        if explorable_content == 0:
            warnings.append(ActionWarning(
                message="探索できるものが見つかりません",
                warning_type="condition",
                is_blocking=False  # 警告だが実行は可能
            ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        warnings = self.can_execute(agent, spot, world)
        
        # ブロッキング警告がある場合は失敗
        if any(w.is_blocking for w in warnings):
            return ActionResult(
                success=False,
                message="探索に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 探索実行（簡易実装）
        discovered_items = []
        discovered_monsters = []
        experience_gained = 5  # 基本経験値
        
        # アイテム発見
        if spot.get_items():
            item = spot.get_items()[0]  # 簡易的に最初のアイテムを発見
            spot.remove_item(item)
            agent.add_item(item)
            discovered_items.append(item.item_id)
        
        # 隠れモンスター発見
        for monster_id, monster in spot.hidden_monsters.items():
            if len(discovered_monsters) == 0:  # 1体のみ発見
                spot.reveal_hidden_monster(monster_id)
                discovered_monsters.append(monster_id)
                break
        
        agent.add_experience_points(experience_gained)
        
        result_message = "探索を行いました"
        if discovered_items:
            result_message += f"、{len(discovered_items)}個のアイテムを発見"
        if discovered_monsters:
            result_message += f"、{len(discovered_monsters)}体のモンスターを発見"
        
        return ActionResult(
            success=True,
            message=result_message,
            warnings=warnings,
            state_changes={
                "items_discovered": discovered_items,
                "monsters_revealed": discovered_monsters
            },
            items_gained=discovered_items,
            experience_gained=experience_gained
        ) 