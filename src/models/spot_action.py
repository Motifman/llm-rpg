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
            JobType.MERCHANT: Permission.CUSTOMER,
            JobType.CRAFTSMAN: Permission.CUSTOMER,
            JobType.ADVENTURER: Permission.CUSTOMER,
            JobType.PRODUCER: Permission.CUSTOMER,
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