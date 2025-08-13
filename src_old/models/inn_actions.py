"""
宿屋系SpotActionの実装

宿泊や回復サービスなどの宿屋固有機能を実装
"""

from typing import Dict, List, Optional, Any
from .spot_action import SpotAction, ActionResult, ActionWarning, Permission


class StayOvernightAction(SpotAction):
    """宿泊行動"""
    
    def __init__(self, room_rate: int = 50):
        super().__init__(
            action_id="stay_overnight",
            name="宿泊",
            description=f"1泊{room_rate}ゴールドで宿泊する",
            required_permission=Permission.CUSTOMER
        )
        self.room_rate = room_rate
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 資金チェック
        if agent.get_money() < self.room_rate:
            warnings.append(ActionWarning(
                message=f"資金不足: {self.room_rate}ゴールド必要、{agent.get_money()}ゴールド所持",
                warning_type="resource",
                is_blocking=True
            ))
        
        # 空室チェック
        if hasattr(spot, 'get_available_rooms'):
            available_rooms = spot.get_available_rooms()
            if available_rooms <= 0:
                warnings.append(ActionWarning(
                    message="満室のため宿泊できません",
                    warning_type="condition",
                    is_blocking=True
                ))
        
        # 既に宿泊中かチェック
        if hasattr(spot, 'current_guests') and agent.agent_id in spot.current_guests:
            warnings.append(ActionWarning(
                message="既に宿泊中です",
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
                message="宿泊に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 宿泊実行
        # 料金支払い
        agent.add_money(-self.room_rate)
        
        # 部屋を予約
        room_booked = False
        room_id = ""
        if hasattr(spot, 'book_room'):
            room_booked = spot.book_room(agent.agent_id, 1)
            if room_booked and hasattr(spot, 'current_guests'):
                room_id = spot.current_guests[agent.agent_id]["room_id"]
        
        # HP/MP回復（宿泊効果）
        hp_restored = 0
        mp_restored = 0
        if agent.current_hp < agent.max_hp:
            hp_restored = agent.max_hp - agent.current_hp
            agent.current_hp = agent.max_hp
        
        if agent.current_mp < agent.max_mp:
            mp_restored = agent.max_mp - agent.current_mp
            agent.current_mp = agent.max_mp
        
        # 店舗収入
        if hasattr(spot, 'add_revenue'):
            spot.add_revenue(self.room_rate)
        
        message = f"宿泊しました（{room_id}、{self.room_rate}ゴールド）"
        if hp_restored > 0 or mp_restored > 0:
            message += f"、HP+{hp_restored} MP+{mp_restored} 回復"
        
        return ActionResult(
            success=True,
            message=message,
            warnings=warnings,
            state_changes={
                "room_booked": room_id,
                "hp_restored": hp_restored,
                "mp_restored": mp_restored
            },
            money_change=-self.room_rate
        )


class HealingServiceAction(SpotAction):
    """回復サービス行動"""
    
    def __init__(self, service_price: int = 30):
        super().__init__(
            action_id="healing_service",
            name="回復サービス",
            description=f"{service_price}ゴールドでHP/MPを回復する",
            required_permission=Permission.CUSTOMER
        )
        self.service_price = service_price
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 資金チェック
        if agent.get_money() < self.service_price:
            warnings.append(ActionWarning(
                message=f"資金不足: {self.service_price}ゴールド必要、{agent.get_money()}ゴールド所持",
                warning_type="resource",
                is_blocking=True
            ))
        
        # 回復の必要性チェック
        if agent.current_hp >= agent.max_hp and agent.current_mp >= agent.max_mp:
            warnings.append(ActionWarning(
                message="HP/MPは既に満タンです",
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
                message="回復サービスに失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 回復サービス実行
        # 料金支払い
        agent.add_money(-self.service_price)
        
        # HP/MP回復
        hp_restored = 0
        mp_restored = 0
        
        if agent.current_hp < agent.max_hp:
            hp_restored = agent.max_hp - agent.current_hp
            agent.current_hp = agent.max_hp
        
        if agent.current_mp < agent.max_mp:
            mp_restored = agent.max_mp - agent.current_mp
            agent.current_mp = agent.max_mp
        
        # 状態異常も治療
        status_cured = len(agent.status_conditions)
        agent.status_conditions.clear()
        
        # 店舗収入
        if hasattr(spot, 'add_revenue'):
            spot.add_revenue(self.service_price)
        
        message = f"回復サービスを受けました（{self.service_price}ゴールド）"
        if hp_restored > 0 or mp_restored > 0:
            message += f"、HP+{hp_restored} MP+{mp_restored} 回復"
        if status_cured > 0:
            message += f"、状態異常{status_cured}個治療"
        
        return ActionResult(
            success=True,
            message=message,
            warnings=warnings,
            state_changes={
                "hp_restored": hp_restored,
                "mp_restored": mp_restored,
                "status_cured": status_cured
            },
            money_change=-self.service_price
        )


class CheckoutAction(SpotAction):
    """チェックアウト行動"""
    
    def __init__(self):
        super().__init__(
            action_id="checkout",
            name="チェックアウト",
            description="宿屋からチェックアウトする",
            required_permission=Permission.CUSTOMER
        )
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 宿泊中かチェック
        if not (hasattr(spot, 'current_guests') and agent.agent_id in spot.current_guests):
            warnings.append(ActionWarning(
                message="現在宿泊していません",
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
                message="チェックアウトに失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # チェックアウト実行
        room_id = ""
        if hasattr(spot, 'current_guests') and agent.agent_id in spot.current_guests:
            room_id = spot.current_guests[agent.agent_id]["room_id"]
        
        if hasattr(spot, 'checkout'):
            spot.checkout(agent.agent_id)
        
        return ActionResult(
            success=True,
            message=f"チェックアウトしました（{room_id}）",
            warnings=warnings,
            state_changes={
                "checked_out_from": room_id
            }
        ) 