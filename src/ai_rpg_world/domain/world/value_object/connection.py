from dataclasses import dataclass
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.movement_cost import MovementCost
from ai_rpg_world.domain.world.exception.map_exception import InvalidConnectionException


@dataclass(frozen=True)
class Connection:
    """スポット間の接続（意味層）"""
    source_id: SpotId
    destination_id: SpotId
    cost: MovementCost = MovementCost.normal()

    def __post_init__(self):
        if self.source_id == self.destination_id:
            raise InvalidConnectionException("Source and destination spots must be different")
