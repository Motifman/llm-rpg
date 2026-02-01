from typing import Dict, Any, Optional
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.entity.world_object_component import WorldObjectComponent


class WorldObject:
    """マップ上の相互作用オブジェクト（チェスト、ドア等）"""
    def __init__(
        self,
        object_id: WorldObjectId,
        coordinate: Coordinate,
        object_type: ObjectTypeEnum,
        is_blocking: bool = True,
        component: Optional[WorldObjectComponent] = None
    ):
        self._object_id = object_id
        self._coordinate = coordinate
        self._object_type = object_type
        self._is_blocking = is_blocking
        self._component = component

    @property
    def object_id(self) -> WorldObjectId:
        return self._object_id

    @property
    def coordinate(self) -> Coordinate:
        return self._coordinate

    @property
    def object_type(self) -> ObjectTypeEnum:
        return self._object_type

    @property
    def is_blocking(self) -> bool:
        return self._is_blocking

    @property
    def component(self) -> Optional[WorldObjectComponent]:
        return self._component

    def set_blocking(self, is_blocking: bool):
        """ブロッキング状態を更新する（例：ドアが開いた）"""
        self._is_blocking = is_blocking
    
    def move_to(self, new_coordinate: Coordinate):
        """オブジェクトを移動させる（例：動く像）"""
        self._coordinate = new_coordinate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": str(self._object_id),
            "coordinate": {"x": self._coordinate.x, "y": self._coordinate.y},
            "object_type": self._object_type.value,
            "is_blocking": self._is_blocking,
            "component": self._component.to_dict() if self._component else None
        }
