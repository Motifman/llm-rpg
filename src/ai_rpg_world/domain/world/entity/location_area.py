from typing import Optional
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.area import Area
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class LocationArea:
    """スポット内の一部の区画（教室、広場の一部など）を表現し、詳細情報を提供する"""
    
    def __init__(
        self, 
        location_id: LocationAreaId,
        area: Area,
        name: str,
        description: str,
        is_active: bool = True
    ):
        self._location_id = location_id
        self._area = area
        self._name = name
        self._description = description
        self._is_active = is_active

    @property
    def location_id(self) -> LocationAreaId:
        return self._location_id

    @property
    def area(self) -> Area:
        return self._area

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def is_active(self) -> bool:
        return self._is_active

    def contains(self, coordinate: Coordinate) -> bool:
        return self._is_active and self._area.contains(coordinate)

    def set_active(self, is_active: bool):
        self._is_active = is_active

    def update_info(self, name: Optional[str] = None, description: Optional[str] = None):
        if name is not None:
            self._name = name
        if description is not None:
            self._description = description
