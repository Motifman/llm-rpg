from typing import Optional, List, Dict, Set
from enum import Enum
from .spot import Spot
from .agent import Agent
from .interactable import InteractableObject


class HomePermission(Enum):
    """家への権限レベル"""
    OWNER = "owner"          # 管理者権限（全ての操作が可能）
    VISITOR = "visitor"      # 立ち入り権限（閲覧のみ）
    DENIED = "denied"        # 立ち入り拒否


class Home(Spot):
    """
    家クラス - Spotを継承した特別な場所
    
    家は個人の所有物で、権限によってアクセス制御される。
    家の中には必ず自分の部屋があり、ベッドと机が置かれている。
    """
    
    def __init__(self, home_id: str, name: str, description: str, 
                 owner_agent_id: str, price: int = 0, parent_spot_id: Optional[str] = None):
        super().__init__(home_id, name, description, parent_spot_id)
        
        # 家固有の属性
        self.owner_agent_id = owner_agent_id
        self.price = price
        
        # 権限管理
        self.permissions: Dict[str, HomePermission] = {
            owner_agent_id: HomePermission.OWNER
        }
        
        # 家の状態
        self.is_locked = True  # デフォルトで施錠されている
        
        # 日記システム
        self.diary_entries: List[Dict] = []  # {"date": str, "content": str, "agent_id": str}
        
        # 家に置かれたアイテム（装飾品など）
        self.stored_items: List = []  # 持ち歩く必要がないアイテム
    
    def get_owner_id(self) -> str:
        """家の所有者IDを取得"""
        return self.owner_agent_id
    
    def get_price(self) -> int:
        """家の価格を取得"""
        return self.price
    
    def set_permission(self, agent_id: str, permission: HomePermission):
        """エージェントに権限を設定"""
        self.permissions[agent_id] = permission
    
    def get_permission(self, agent_id: str) -> HomePermission:
        """エージェントの権限を取得"""
        return self.permissions.get(agent_id, HomePermission.DENIED)
    
    def has_owner_permission(self, agent_id: str) -> bool:
        """管理者権限を持っているかチェック"""
        return self.get_permission(agent_id) == HomePermission.OWNER
    
    def has_visitor_permission(self, agent_id: str) -> bool:
        """立ち入り権限以上を持っているかチェック"""
        permission = self.get_permission(agent_id)
        return permission in [HomePermission.OWNER, HomePermission.VISITOR]
    
    def can_enter(self, agent_id: str) -> bool:
        """家に入ることができるかチェック"""
        if not self.is_locked:
            return True
        return self.has_visitor_permission(agent_id)
    
    def lock_home(self, agent_id: str) -> bool:
        """家に鍵をかける（所有者のみ）"""
        if self.has_owner_permission(agent_id):
            self.is_locked = True
            return True
        return False
    
    def unlock_home(self, agent_id: str) -> bool:
        """家の鍵を開ける（権限を持つ者のみ）"""
        if self.has_visitor_permission(agent_id):
            self.is_locked = False
            return True
        return False
    
    def add_diary_entry(self, agent_id: str, content: str, date: str) -> bool:
        """日記エントリを追加（所有者のみ）"""
        if self.has_owner_permission(agent_id):
            entry = {
                "date": date,
                "content": content,
                "agent_id": agent_id
            }
            self.diary_entries.append(entry)
            return True
        return False
    
    def get_diary_entries(self, agent_id: str) -> List[Dict]:
        """日記エントリを取得（立ち入り権限以上で可能）"""
        if self.has_visitor_permission(agent_id):
            return self.diary_entries.copy()
        return []
    
    def store_item(self, agent_id: str, item) -> bool:
        """アイテムを家に置く（所有者のみ）"""
        if self.has_owner_permission(agent_id):
            self.stored_items.append(item)
            return True
        return False
    
    def retrieve_item(self, agent_id: str, item) -> bool:
        """アイテムを家から取る（所有者のみ）"""
        if self.has_owner_permission(agent_id) and item in self.stored_items:
            self.stored_items.remove(item)
            return True
        return False
    
    def get_stored_items(self, agent_id: str) -> List:
        """保管されたアイテムを取得（立ち入り権限以上で可能）"""
        if self.has_visitor_permission(agent_id):
            return self.stored_items.copy()
        return []
    
    def calculate_price_by_room_count(self) -> int:
        """部屋数に基づいて家の価格を計算"""
        # 基本価格（自分の部屋）
        base_price = 1000
        
        # 追加部屋数（子スポット数）
        additional_rooms = len(self.child_spots)
        room_price = 500
        
        total_price = base_price + (additional_rooms * room_price)
        return total_price
    
    def update_price(self):
        """部屋数に基づいて価格を更新"""
        self.price = self.calculate_price_by_room_count() 