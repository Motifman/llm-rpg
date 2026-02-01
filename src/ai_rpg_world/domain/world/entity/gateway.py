from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.area import Area
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class Gateway:
    """スポットの出入り口（ゲートウェイ）を表現する"""
    
    def __init__(
        self,
        gateway_id: GatewayId,
        name: str,
        area: Area,
        target_spot_id: SpotId,
        landing_coordinate: Coordinate,
        is_active: bool = True
    ):
        self._gateway_id = gateway_id
        self._name = name
        self._area = area
        self._target_spot_id = target_spot_id
        self._landing_coordinate = landing_coordinate
        self._is_active = is_active

    @property
    def gateway_id(self) -> GatewayId:
        return self._gateway_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def area(self) -> Area:
        return self._area

    @property
    def target_spot_id(self) -> SpotId:
        return self._target_spot_id

    @property
    def landing_coordinate(self) -> Coordinate:
        return self._landing_coordinate

    @property
    def is_active(self) -> bool:
        return self._is_active

    def contains(self, coordinate: Coordinate) -> bool:
        """指定された座標が出口範囲内にあるか"""
        return self._is_active and self._area.contains(coordinate)

    def set_active(self, is_active: bool):
        self._is_active = is_active
