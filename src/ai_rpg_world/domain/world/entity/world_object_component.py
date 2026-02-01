from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability


class WorldObjectComponent(ABC):
    """ワールドオブジェクトの機能を定義するコンポーネントの基底クラス"""
    
    @abstractmethod
    def get_type_name(self) -> str:
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


class ChestComponent(WorldObjectComponent):
    """宝箱の機能を持つコンポーネント"""
    def __init__(self, is_open: bool = False, item_ids: list[int] = None):
        self.is_open = is_open
        self.item_ids = item_ids or []

    def get_type_name(self) -> str:
        return "chest"

    def open(self):
        self.is_open = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_open": self.is_open,
            "item_ids": self.item_ids
        }


class DoorComponent(WorldObjectComponent):
    """ドアの機能を持つコンポーネント"""
    def __init__(self, is_open: bool = False, is_locked: bool = False):
        self.is_open = is_open
        self.is_locked = is_locked

    def get_type_name(self) -> str:
        return "door"

    def open(self):
        if self.is_locked:
            raise LockedDoorException("Door is locked")
        self.is_open = True

    def unlock(self):
        self.is_locked = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_open": self.is_open,
            "is_locked": self.is_locked
        }


class ActorComponent(WorldObjectComponent):
    """プレイヤーやNPCなどの動体（アクター）の機能を持つコンポーネント"""
    def __init__(
        self, 
        direction: DirectionEnum = DirectionEnum.SOUTH,
        capability: MovementCapability = None,
        owner_id: Optional[str] = None, # プレイヤーIDなど
        is_npc: bool = False
    ):
        self.direction = direction
        self.capability = capability or MovementCapability.normal_walk()
        self.owner_id = owner_id
        self.is_npc = is_npc

    def get_type_name(self) -> str:
        return "actor"

    def turn(self, direction: DirectionEnum):
        self.direction = direction

    def update_capability(self, capability: MovementCapability):
        self.capability = capability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value,
            "speed_modifier": self.capability.speed_modifier,
            "capabilities": [c.value for c in self.capability.capabilities],
            "owner_id": self.owner_id,
            "is_npc": self.is_npc
        }


class InteractableComponent(WorldObjectComponent):
    """インタラクション（調べる、話しかける等）が可能なコンポーネント"""
    def __init__(self, interaction_type: str, data: Dict[str, Any] = None):
        self.interaction_type = interaction_type
        self.data = data or {}

    def get_type_name(self) -> str:
        return "interactable"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interaction_type": self.interaction_type,
            "data": self.data
        }
