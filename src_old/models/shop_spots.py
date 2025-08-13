"""
商店系Spotクラスの実装

各種商店をSpotを継承して実装
"""

from typing import Dict, List, Optional, Any
from .spot import Spot
from .spot_action import Role, Permission
from .shop_actions import BuyItemSpotAction, SellItemSpotAction, ViewInventorySpotAction, SetItemPriceSpotAction


class ShopSpot(Spot):
    """商店の基底クラス"""
    
    def __init__(self, spot_id: str, name: str, description: str, 
                 shop_type: str = "general", parent_spot_id: Optional[str] = None):
        super().__init__(spot_id, name, description, parent_spot_id)
        
        # 商店固有の属性
        self.shop_type = shop_type
        self.shop_inventory: Dict[str, int] = {}  # item_id -> quantity
        self.item_prices: Dict[str, Dict[str, int]] = {}  # item_id -> {buy_price, sell_price}
        self.revenue: int = 0  # 店舗収益
        self.shop_owner_id: Optional[str] = None  # 店主のエージェントID
        
        # 商店用権限設定
        self._setup_shop_permissions()
        
        # 基本商店行動を追加
        self._add_shop_actions()
    
    def _setup_shop_permissions(self):
        """商店用の権限設定"""
        # 基本的な権限設定
        self.set_role_permission(Role.CITIZEN, Permission.CUSTOMER)
        self.set_role_permission(Role.ADVENTURER, Permission.CUSTOMER)
        self.set_role_permission(Role.MERCHANT, Permission.CUSTOMER)
        self.set_role_permission(Role.SHOP_KEEPER, Permission.OWNER)
    
    def _add_shop_actions(self):
        """基本的な商店行動を追加"""
        # 在庫確認行動
        view_action = ViewInventorySpotAction()
        self.add_spot_action(view_action)
    
    def set_shop_owner(self, agent_id: str):
        """店主を設定"""
        self.shop_owner_id = agent_id
        self.set_agent_permission(agent_id, Permission.OWNER)
    
    def add_inventory(self, item_id: str, quantity: int):
        """在庫を追加"""
        if item_id in self.shop_inventory:
            self.shop_inventory[item_id] += quantity
        else:
            self.shop_inventory[item_id] = quantity
    
    def remove_inventory(self, item_id: str, quantity: int) -> int:
        """在庫を削除（実際に削除された数を返す）"""
        if item_id not in self.shop_inventory:
            return 0
        
        available = self.shop_inventory[item_id]
        removed = min(available, quantity)
        self.shop_inventory[item_id] -= removed
        
        if self.shop_inventory[item_id] <= 0:
            del self.shop_inventory[item_id]
        
        return removed
    
    def set_item_price(self, item_id: str, buy_price: int, sell_price: int):
        """商品価格を設定"""
        self.item_prices[item_id] = {
            'buy_price': buy_price,
            'sell_price': sell_price
        }
        
        # 動的に購入・売却行動を追加
        self._update_item_actions(item_id)
    
    def _update_item_actions(self, item_id: str):
        """特定アイテムの購入・売却行動を動的に追加/更新"""
        if item_id in self.item_prices:
            prices = self.item_prices[item_id]
            
            # 購入行動を追加/更新
            buy_action = BuyItemSpotAction(
                item_id=item_id,
                quantity=1,
                price_per_item=prices['buy_price']
            )
            self.add_spot_action(buy_action)
            
            # 売却行動を追加/更新
            sell_action = SellItemSpotAction(
                item_id=item_id,
                quantity=1,
                price_per_item=prices['sell_price']
            )
            self.add_spot_action(sell_action)
    
    def add_revenue(self, amount: int):
        """店舗収益を追加"""
        self.revenue += amount
    
    def get_revenue(self) -> int:
        """店舗収益を取得"""
        return self.revenue


class ItemShopSpot(ShopSpot):
    """雑貨屋（一般的なアイテムショップ）"""
    
    def __init__(self, spot_id: str, name: str, description: str, parent_spot_id: Optional[str] = None):
        super().__init__(spot_id, name, description, "item_shop", parent_spot_id)
        
        # 雑貨屋用の初期在庫と価格設定
        self._setup_initial_inventory()
    
    def _setup_initial_inventory(self):
        """初期在庫と価格を設定"""
        initial_items = [
            ("herb", 20, 15, 8),         # 薬草: 在庫20、購入15G、売却8G
            ("bread", 15, 10, 5),        # パン: 在庫15、購入10G、売却5G
            ("water", 30, 5, 2),         # 水: 在庫30、購入5G、売却2G
            ("rope", 5, 25, 15),         # ロープ: 在庫5、購入25G、売却15G
        ]
        
        for item_id, stock, buy_price, sell_price in initial_items:
            self.add_inventory(item_id, stock)
            self.set_item_price(item_id, buy_price, sell_price)


class WeaponShopSpot(ShopSpot):
    """武器屋"""
    
    def __init__(self, spot_id: str, name: str, description: str, parent_spot_id: Optional[str] = None):
        super().__init__(spot_id, name, description, "weapon_shop", parent_spot_id)
        
        # 武器屋用の権限設定
        self.set_role_permission(Role.BLACKSMITH, Permission.EMPLOYEE)
        
        # 武器屋用の初期在庫と価格設定
        self._setup_initial_inventory()
    
    def _setup_initial_inventory(self):
        """初期在庫と価格を設定"""
        initial_weapons = [
            ("iron_sword", 3, 150, 100),      # 鉄の剣: 在庫3、購入150G、売却100G
            ("wooden_shield", 5, 80, 50),     # 木の盾: 在庫5、購入80G、売却50G
            ("steel_dagger", 4, 120, 80),     # 鋼の短剣: 在庫4、購入120G、売却80G
            ("leather_armor", 2, 200, 120),   # 革の鎧: 在庫2、購入200G、売却120G
        ]
        
        for item_id, stock, buy_price, sell_price in initial_weapons:
            self.add_inventory(item_id, stock)
            self.set_item_price(item_id, buy_price, sell_price)


class InnSpot(ShopSpot):
    """宿屋"""
    
    def __init__(self, spot_id: str, name: str, description: str, parent_spot_id: Optional[str] = None):
        super().__init__(spot_id, name, description, "inn", parent_spot_id)
        
        # 宿屋固有の属性
        self.room_capacity = 10  # 部屋数
        self.current_guests: Dict[str, Dict] = {}  # agent_id -> {room_id, nights_remaining}
        self.room_rate = 50  # 1泊の料金
        
        # 宿屋用の権限設定
        self.set_role_permission(Role.INNKEEPER, Permission.OWNER)
        
        # 宿屋固有の行動を追加
        self._add_inn_actions()
    
    def _add_inn_actions(self):
        """宿屋固有の行動を追加"""
        from .inn_actions import StayOvernightAction, HealingServiceAction
        
        # 宿泊行動
        stay_action = StayOvernightAction(self.room_rate)
        self.add_spot_action(stay_action)
        
        # 回復サービス行動
        healing_action = HealingServiceAction(30)  # 30ゴールドで回復
        self.add_spot_action(healing_action)
    
    def book_room(self, agent_id: str, nights: int = 1) -> bool:
        """部屋を予約"""
        if len(self.current_guests) >= self.room_capacity:
            return False  # 満室
        
        if agent_id in self.current_guests:
            return False  # 既に宿泊中
        
        room_id = f"room_{len(self.current_guests) + 1}"
        self.current_guests[agent_id] = {
            "room_id": room_id,
            "nights_remaining": nights
        }
        return True
    
    def checkout(self, agent_id: str):
        """チェックアウト"""
        if agent_id in self.current_guests:
            del self.current_guests[agent_id]
    
    def get_available_rooms(self) -> int:
        """利用可能な部屋数を取得"""
        return self.room_capacity - len(self.current_guests) 