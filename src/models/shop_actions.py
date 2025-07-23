"""
商店系SpotActionの実装

基本的な商店機能をSpotActionとして実装
"""

from typing import Dict, List, Optional, Any
from .spot_action import SpotAction, ActionResult, ActionWarning, Permission
from .item import Item


class BuyItemSpotAction(SpotAction):
    """アイテム購入行動"""
    
    def __init__(self, item_id: str, quantity: int = 1, price_per_item: int = 10):
        super().__init__(
            action_id=f"buy_{item_id}",
            name=f"{item_id}を購入",
            description=f"{item_id}を{quantity}個購入する",
            required_permission=Permission.CUSTOMER
        )
        self.item_id = item_id
        self.quantity = quantity
        self.price_per_item = price_per_item
        self.total_price = price_per_item * quantity
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 資金チェック
        if agent.get_money() < self.total_price:
            warnings.append(ActionWarning(
                message=f"資金不足: {self.total_price}ゴールド必要、{agent.get_money()}ゴールド所持",
                warning_type="resource",
                is_blocking=True
            ))
        
        # 店舗在庫チェック（Spotが商店の場合）
        if hasattr(spot, 'shop_inventory'):
            available_stock = spot.shop_inventory.get(self.item_id, 0)
            if available_stock < self.quantity:
                warnings.append(ActionWarning(
                    message=f"在庫不足: {self.quantity}個必要、{available_stock}個在庫",
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
                message="購入に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 購入実行
        # 金銭支払い
        agent.add_money(-self.total_price)
        
        # アイテム取得
        purchased_items = []
        for _ in range(self.quantity):
            item = Item(self.item_id, f"購入した{self.item_id}")
            agent.add_item(item)
            purchased_items.append(self.item_id)
        
        # 店舗在庫から減算（商店の場合）
        if hasattr(spot, 'shop_inventory'):
            spot.shop_inventory[self.item_id] -= self.quantity
            if spot.shop_inventory[self.item_id] <= 0:
                del spot.shop_inventory[self.item_id]
        
        # 店舗収入（店主への収益分配）
        if hasattr(spot, 'add_revenue'):
            spot.add_revenue(self.total_price)
        
        return ActionResult(
            success=True,
            message=f"{self.item_id}を{self.quantity}個購入しました（{self.total_price}ゴールド）",
            warnings=warnings,
            state_changes={
                "items_purchased": purchased_items,
                "money_spent": self.total_price
            },
            items_gained=purchased_items,
            money_change=-self.total_price
        )


class SellItemSpotAction(SpotAction):
    """アイテム売却行動"""
    
    def __init__(self, item_id: str, quantity: int = 1, price_per_item: int = 5):
        super().__init__(
            action_id=f"sell_{item_id}",
            name=f"{item_id}を売却",
            description=f"{item_id}を{quantity}個売却する",
            required_permission=Permission.CUSTOMER
        )
        self.item_id = item_id
        self.quantity = quantity
        self.price_per_item = price_per_item
        self.total_price = price_per_item * quantity
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # アイテム所持チェック
        owned_count = agent.get_item_count(self.item_id)
        if owned_count < self.quantity:
            warnings.append(ActionWarning(
                message=f"アイテム不足: {self.quantity}個必要、{owned_count}個所持",
                warning_type="resource",
                is_blocking=True
            ))
        
        return warnings
    
    def execute(self, agent, spot, world=None) -> ActionResult:
        warnings = self.can_execute(agent, spot, world)
        
        # ブロッキング警告がある場合は失敗
        if any(w.is_blocking for w in warnings):
            return ActionResult(
                success=False,
                message="売却に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 売却実行
        # アイテム削除
        removed_count = agent.remove_item_by_id(self.item_id, self.quantity)
        if removed_count != self.quantity:
            return ActionResult(
                success=False,
                message="アイテムの削除に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 金銭取得
        agent.add_money(self.total_price)
        
        # 店舗在庫に追加（商店の場合）
        if hasattr(spot, 'shop_inventory'):
            if self.item_id in spot.shop_inventory:
                spot.shop_inventory[self.item_id] += self.quantity
            else:
                spot.shop_inventory[self.item_id] = self.quantity
        
        sold_items = [self.item_id] * self.quantity
        
        return ActionResult(
            success=True,
            message=f"{self.item_id}を{self.quantity}個売却しました（{self.total_price}ゴールド獲得）",
            warnings=warnings,
            state_changes={
                "items_sold": sold_items,
                "money_gained": self.total_price
            },
            items_lost=sold_items,
            money_change=self.total_price
        )


class ViewInventorySpotAction(SpotAction):
    """在庫確認行動"""
    
    def __init__(self):
        super().__init__(
            action_id="view_inventory",
            name="在庫確認",
            description="店舗の在庫と価格を確認する",
            required_permission=Permission.GUEST
        )
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 商店かどうかチェック
        if not hasattr(spot, 'shop_inventory'):
            warnings.append(ActionWarning(
                message="この場所では在庫確認ができません",
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
                message="在庫確認に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 在庫情報の取得
        inventory_info = {}
        if hasattr(spot, 'shop_inventory'):
            inventory_info = spot.shop_inventory.copy()
        
        # 価格情報の取得
        price_info = {}
        if hasattr(spot, 'item_prices'):
            price_info = spot.item_prices.copy()
        
        # 在庫表示メッセージの生成
        if inventory_info:
            message = "【在庫一覧】\n"
            for item_id, stock in inventory_info.items():
                price = price_info.get(item_id, "価格未設定")
                message += f"- {item_id}: {stock}個 ({price}ゴールド)\n"
        else:
            message = "在庫はありません"
        
        return ActionResult(
            success=True,
            message=message,
            warnings=warnings,
            state_changes={},
            additional_data={
                "inventory": inventory_info,
                "prices": price_info
            }
        )


class SetItemPriceSpotAction(SpotAction):
    """商品価格設定行動（店主専用）"""
    
    def __init__(self, item_id: str, buy_price: int, sell_price: int):
        super().__init__(
            action_id=f"set_price_{item_id}",
            name=f"{item_id}の価格設定",
            description=f"{item_id}の購入・売却価格を設定する",
            required_permission=Permission.OWNER
        )
        self.item_id = item_id
        self.buy_price = buy_price  # 顧客が購入する価格
        self.sell_price = sell_price  # 顧客から買い取る価格
    
    def can_execute(self, agent, spot, world=None) -> List[ActionWarning]:
        warnings = []
        
        # 権限チェック（店主のみ）
        warnings.extend(self.check_permission(agent, spot.permission_checker))
        
        # 価格設定の妥当性チェック
        if self.buy_price <= 0 or self.sell_price <= 0:
            warnings.append(ActionWarning(
                message="価格は0より大きい値を設定してください",
                warning_type="condition",
                is_blocking=True
            ))
        
        if self.sell_price >= self.buy_price:
            warnings.append(ActionWarning(
                message="売却価格は購入価格より低く設定することを推奨します",
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
                message="価格設定に失敗しました",
                warnings=warnings,
                state_changes={}
            )
        
        # 価格設定の実行
        if not hasattr(spot, 'item_prices'):
            spot.item_prices = {}
        
        spot.item_prices[self.item_id] = {
            'buy_price': self.buy_price,
            'sell_price': self.sell_price
        }
        
        return ActionResult(
            success=True,
            message=f"{self.item_id}の価格を設定しました（購入: {self.buy_price}G、売却: {self.sell_price}G）",
            warnings=warnings,
            state_changes={
                "price_updated": {
                    "item_id": self.item_id,
                    "buy_price": self.buy_price,
                    "sell_price": self.sell_price
                }
            }
        ) 