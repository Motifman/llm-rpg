from abc import ABC, abstractmethod
from typing import Any

from ai_rpg_world.domain.world.enum.world_enum import TriggerTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class MapTrigger(ABC):
    """タイルに進入した際に発火するトリガーの基底クラス"""
    
    @abstractmethod
    def get_trigger_type(self) -> TriggerTypeEnum:
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """永続化やイベント送信用の辞書形式に変換する"""
        pass


class WarpTrigger(MapTrigger):
    """別の場所へ移動させるトリガー"""
    def __init__(self, target_spot_id: SpotId, target_coordinate: Coordinate):
        self.target_spot_id = target_spot_id
        self.target_coordinate = target_coordinate

    def get_trigger_type(self) -> TriggerTypeEnum:
        return TriggerTypeEnum.WARP

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.get_trigger_type().value,
            "target_spot_id": str(self.target_spot_id),
            "target_coordinate": {
                "x": self.target_coordinate.x, 
                "y": self.target_coordinate.y,
                "z": self.target_coordinate.z
            }
        }


class DamageTrigger(MapTrigger):
    """ダメージを与えるトリガー（罠など）"""
    def __init__(self, damage: int):
        self.damage = damage

    def get_trigger_type(self) -> TriggerTypeEnum:
        return TriggerTypeEnum.DAMAGE

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.get_trigger_type().value,
            "damage": self.damage
        }
