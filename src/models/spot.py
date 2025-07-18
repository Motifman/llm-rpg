from typing import Optional, List, Dict, Set
from .item import Item
from .action import Movement, Exploration, Interaction
from .interactable import InteractableObject


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
        
        # 階層管理用
        self.child_spots: Set[str] = set()  # 子スポットのID一覧
        self.entry_points: Dict[str, str] = {}  # 入口名 -> そこに入った時の最初のspot_id
        self.exit_to_parent: Optional[str] = None  # 親スポットに戻る時の接続先spot_id
        self.is_entrance: bool = False  # このスポットが親の入口かどうか
        self.entrance_name: Optional[str] = None  # 入口の名前（例：「正面玄関」「裏口」）

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
    
    def get_all_interactables(self) -> List[InteractableObject]:
        """全ての相互作用可能オブジェクトを取得"""
        return list(self.interactables.values())
    
    def get_available_interactions(self) -> List[Interaction]:
        """このSpotで利用可能な全ての相互作用を取得"""
        all_interactions = []
        for interactable in self.interactables.values():
            all_interactions.extend(interactable.get_available_interactions())
        return all_interactions