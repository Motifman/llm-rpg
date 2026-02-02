from typing import Dict, Any, Optional, TYPE_CHECKING
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.entity.world_object_component import WorldObjectComponent

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
    from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability


class WorldObject:
    """マップ上の相互作用オブジェクト（チェスト、ドア等）"""
    def __init__(
        self,
        object_id: WorldObjectId,
        coordinate: Coordinate,
        object_type: ObjectTypeEnum,
        is_blocking: bool = True,
        is_blocking_sight: bool = None,
        component: Optional[WorldObjectComponent] = None
    ):
        self._object_id = object_id
        self._coordinate = coordinate
        self._object_type = object_type
        self._is_blocking = is_blocking
        # 明示的に指定がない場合はis_blockingと同じにする
        self._is_blocking_sight = is_blocking_sight if is_blocking_sight is not None else is_blocking
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
    def is_blocking_sight(self) -> bool:
        return self._is_blocking_sight

    @property
    def component(self) -> Optional[WorldObjectComponent]:
        return self._component

    @property
    def is_actor(self) -> bool:
        """アクターかどうか"""
        return self._component.is_actor if self._component else False

    @property
    def capability(self) -> Optional["MovementCapability"]:
        """移動能力を返す"""
        return self._component.capability if self._component else None

    def turn(self, direction: "DirectionEnum"):
        """向きを変える"""
        if self._component:
            self._component.turn(direction)

    @property
    def direction(self) -> Optional["DirectionEnum"]:
        """向きを返す"""
        return getattr(self._component, "direction", None) if self._component else None

    @property
    def interaction_type(self) -> Optional[str]:
        """インタラクションタイプを返す"""
        return self._component.interaction_type if self._component else None

    @property
    def interaction_data(self) -> Dict[str, Any]:
        """インタラクションデータを返す"""
        return self._component.interaction_data if self._component else {}

    def set_blocking(self, is_blocking: bool):
        """ブロッキング状態を更新する（例：ドアが開いた）"""
        self._is_blocking = is_blocking

    def set_blocking_sight(self, is_blocking_sight: bool):
        """視覚遮蔽状態を更新する"""
        self._is_blocking_sight = is_blocking_sight
    
    def move_to(self, new_coordinate: Coordinate):
        """オブジェクトを移動させる（例：動く像）"""
        self._coordinate = new_coordinate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": str(self._object_id),
            "coordinate": {"x": self._coordinate.x, "y": self._coordinate.y, "z": self._coordinate.z},
            "object_type": self._object_type.value,
            "is_blocking": self._is_blocking,
            "component": self._component.to_dict() if self._component else None
        }
