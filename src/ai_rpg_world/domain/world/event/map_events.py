from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.connection import Connection
from ai_rpg_world.domain.world.enum.world_enum import TerrainTypeEnum, TriggerTypeEnum


@dataclass(frozen=True)
class PhysicalMapCreatedEvent(BaseDomainEvent[SpotId, str]):
    """物理マップが作成されたイベント"""
    spot_id: SpotId


@dataclass(frozen=True)
class WorldObjectStateChangedEvent(BaseDomainEvent[WorldObjectId, str]):
    """オブジェクトの状態が変化したイベント"""
    object_id: WorldObjectId
    key: str
    new_value: any


@dataclass(frozen=True)
class WorldObjectBlockingChangedEvent(BaseDomainEvent[WorldObjectId, str]):
    """オブジェクトのブロッキング状態が変化したイベント"""
    object_id: WorldObjectId
    is_blocking: bool


@dataclass(frozen=True)
class WorldObjectMovedEvent(BaseDomainEvent[WorldObjectId, str]):
    """オブジェクトが移動したイベント"""
    object_id: WorldObjectId
    from_coordinate: Coordinate
    to_coordinate: Coordinate


@dataclass(frozen=True)
class WorldObjectAddedEvent(BaseDomainEvent[WorldObjectId, str]):
    """オブジェクトが追加されたイベント"""
    object_id: WorldObjectId
    coordinate: Coordinate


@dataclass(frozen=True)
class TileTerrainChangedEvent(BaseDomainEvent[SpotId, str]):
    """タイルの地形が変化したイベント"""
    spot_id: SpotId
    coordinate: Coordinate
    new_terrain_type: TerrainTypeEnum


@dataclass(frozen=True)
class TileTriggeredEvent(BaseDomainEvent[SpotId, str]):
    """タイルのトリガーが発火したイベント"""
    spot_id: SpotId
    coordinate: Coordinate
    trigger_type: TriggerTypeEnum
    object_id: Optional[WorldObjectId] = None


@dataclass(frozen=True)
class WorldMapCreatedEvent(BaseDomainEvent[WorldId, str]):
    """世界地図が作成されたイベント"""
    world_id: WorldId


@dataclass(frozen=True)
class SpotAddedEvent(BaseDomainEvent[WorldId, str]):
    """スポットが追加されたイベント"""
    world_id: WorldId
    spot_id: SpotId


@dataclass(frozen=True)
class ConnectionAddedEvent(BaseDomainEvent[WorldId, str]):
    """接続が追加されたイベント"""
    world_id: WorldId
    connection: Connection
