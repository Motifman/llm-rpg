from typing import List, Dict, Optional
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.connection import Connection
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.event.map_events import (
    WorldMapCreatedEvent,
    SpotAddedEvent,
    ConnectionAddedEvent
)
from ai_rpg_world.domain.world.exception.map_exception import (
    SpotNotFoundException,
    InvalidConnectionException
)


class WorldMapAggregate(AggregateRoot):
    """世界地図（意味マップ）の集約。スポット間の接続グラフを管理する。"""
    
    def __init__(
        self,
        world_id: WorldId,
        spots: List[Spot] = None,
        connections: List[Connection] = None
    ):
        super().__init__()
        self._world_id = world_id
        self._spots: Dict[SpotId, Spot] = {spot.spot_id: spot for spot in (spots or [])}
        self._connections: List[Connection] = connections or []

    @classmethod
    def create(cls, world_id: WorldId, spots: List[Spot] = None, connections: List[Connection] = None) -> "WorldMapAggregate":
        aggregate = cls(world_id, spots, connections)
        aggregate.add_event(WorldMapCreatedEvent.create(
            aggregate_id=world_id,
            aggregate_type="WorldMapAggregate",
            world_id=world_id
        ))
        return aggregate

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def add_spot(self, spot: Spot):
        self._spots[spot.spot_id] = spot
        self.add_event(SpotAddedEvent.create(
            aggregate_id=self._world_id,
            aggregate_type="WorldMapAggregate",
            world_id=self._world_id,
            spot_id=spot.spot_id
        ))

    def get_spot(self, spot_id: SpotId) -> Spot:
        if spot_id not in self._spots:
            raise SpotNotFoundException(f"Spot {spot_id} not found in world {self._world_id}")
        return self._spots[spot_id]

    def add_connection(self, connection: Connection):
        # 1. 接続先のスポットが存在するかチェック
        if connection.source_id not in self._spots:
            raise SpotNotFoundException(f"Source spot {connection.source_id} not found")
        if connection.destination_id not in self._spots:
            raise SpotNotFoundException(f"Destination spot {connection.destination_id} not found")
            
        # 2. 自己接続の禁止
        if connection.source_id == connection.destination_id:
            raise InvalidConnectionException("Cannot connect a spot to itself")

        # 3. 重複接続は許容する仕様（異なるコストやルートがあり得るため）
        
        self._connections.append(connection)
        self.add_event(ConnectionAddedEvent.create(
            aggregate_id=self._world_id,
            aggregate_type="WorldMapAggregate",
            world_id=self._world_id,
            connection=connection
        ))

    def get_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        """指定されたスポットから移動可能なスポットのリストを取得"""
        connected = []
        for conn in self._connections:
            if conn.source_id == spot_id:
                connected.append(conn.destination_id)
        return connected

    def get_all_spots(self) -> List[Spot]:
        return list(self._spots.values())

    def get_all_connections(self) -> List[Connection]:
        return self._connections.copy()
