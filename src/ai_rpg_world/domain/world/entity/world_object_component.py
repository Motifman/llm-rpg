from abc import ABC, abstractmethod
from typing import Dict, Any
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException


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
