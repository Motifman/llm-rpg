from typing import Optional
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.area import Area
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.map_trigger import MapTrigger


class AreaTrigger:
    """特定のエリアに対して効果を発動するトリガー"""
    
    def __init__(
        self, 
        trigger_id: AreaTriggerId,
        area: Area,
        trigger: MapTrigger,
        name: str = "",
        is_active: bool = True
    ):
        self._trigger_id = trigger_id
        self._area = area
        self._trigger = trigger
        self._name = name
        self._is_active = is_active

    @property
    def trigger_id(self) -> AreaTriggerId:
        return self._trigger_id

    @property
    def area(self) -> Area:
        return self._area

    @property
    def trigger(self) -> MapTrigger:
        return self._trigger

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_active(self) -> bool:
        return self._is_active

    def contains(self, coordinate: Coordinate) -> bool:
        return self._is_active and self._area.contains(coordinate)

    def set_active(self, is_active: bool):
        self._is_active = is_active
