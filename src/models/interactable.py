from .agent import Agent
from .item import Item
from .action import InteractionType, Interaction, Movement
from .reward import ActionReward
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod


class InteractableObject(ABC):
    """相互作用可能オブジェクトの基底クラス"""
    
    def __init__(self, object_id: str, name: str, description: str):
        self.object_id = object_id
        self.name = name
        self.description = description
        self.state: Dict[str, Any] = {}
        
    @abstractmethod
    def can_interact(self, agent: Agent, interaction_type: InteractionType) -> bool:
        """この相互作用が実行可能かチェック"""
        pass
        
    @abstractmethod
    def get_available_interactions(self) -> List[Interaction]:
        """利用可能な相互作用のリストを取得"""
        pass
    
    def get_state(self, key: str, default=None):
        """状態値を取得"""
        return self.state.get(key, default)
    
    def set_state(self, key: str, value: Any):
        """状態値を設定"""
        self.state[key] = value
    
    def __str__(self):
        return f"{self.__class__.__name__}(id={self.object_id}, name={self.name})"


class Chest(InteractableObject):
    """宝箱クラス"""
    
    def __init__(self, object_id: str, name: str, description: str, 
                 key_item_id: Optional[str] = None, items: List[Item] = None):
        super().__init__(object_id, name, description)
        self.key_item_id = key_item_id
        self.items: List[Item] = items or []
        
        self.set_state("is_locked", key_item_id is not None)
        self.set_state("is_opened", False)
        
    def can_interact(self, agent: Agent, interaction_type: InteractionType) -> bool:
        """相互作用の実行可否をチェック"""
        if interaction_type == InteractionType.OPEN:
            if self.get_state("is_opened"):
                return False
            if self.get_state("is_locked") and self.key_item_id:
                return agent.has_item(self.key_item_id)
            return True
        elif interaction_type == InteractionType.EXAMINE:
            return True
        return False
    
    def get_available_interactions(self) -> List[Interaction]:
        """利用可能な相互作用を取得"""
        interactions = []
        
        examine_reward = ActionReward(
            information=["宝箱の詳細情報を確認した"]
        )
        interactions.append(Interaction(
            description=f"{self.name}を調べる",
            object_id=self.object_id,
            interaction_type=InteractionType.EXAMINE,
            reward=examine_reward
        ))
        
        if not self.get_state("is_opened"):
            open_reward = ActionReward(
                items=[item.item_id for item in self.items],
                information=[f"{self.name}を開けた"]
            )
            interactions.append(Interaction(
                description=f"{self.name}を開ける",
                object_id=self.object_id,
                interaction_type=InteractionType.OPEN,
                reward=open_reward,
                required_item_id=self.key_item_id,
                state_changes={"is_opened": True, "is_locked": False}
            ))
        
        return interactions


class Door(InteractableObject):
    """ドアクラス"""
    
    def __init__(self, object_id: str, name: str, description: str,
                 target_spot_id: str, key_item_id: Optional[str] = None):
        super().__init__(object_id, name, description)
        self.target_spot_id = target_spot_id
        self.key_item_id = key_item_id
        
        self.set_state("is_locked", key_item_id is not None)
        self.set_state("is_open", False)
    
    def can_interact(self, agent: Agent, interaction_type: InteractionType) -> bool:
        """相互作用の実行可否をチェック"""
        if interaction_type == InteractionType.OPEN:
            if self.get_state("is_locked") and self.key_item_id:
                return agent.has_item(self.key_item_id)
            return not self.get_state("is_open")
        elif interaction_type == InteractionType.EXAMINE:
            return True
        return False
    
    def creates_movement_when_opened(self) -> Optional[Movement]:
        """ドアを開いた時に作成されるMovement情報を返す"""
        if self.get_state("is_open"):
            return Movement(
                description=f"{self.name}を通って移動",
                direction=f"{self.name}を通る",
                target_spot_id=self.target_spot_id
            )
        return None
    
    def get_available_interactions(self) -> List[Interaction]:
        """利用可能な相互作用を取得"""
        interactions = []
        
        examine_reward = ActionReward(
            information=[f"{self.name}の詳細: {self.description}"]
        )
        interactions.append(Interaction(
            description=f"{self.name}を調べる",
            object_id=self.object_id,
            interaction_type=InteractionType.EXAMINE,
            reward=examine_reward
        ))
        
        if not self.get_state("is_open"):
            open_reward = ActionReward(
                information=[f"{self.name}を開けた"]
            )
            interactions.append(Interaction(
                description=f"{self.name}を開ける",
                object_id=self.object_id,
                interaction_type=InteractionType.OPEN,
                reward=open_reward,
                required_item_id=self.key_item_id,
                state_changes={"is_open": True}
            ))
        
        return interactions