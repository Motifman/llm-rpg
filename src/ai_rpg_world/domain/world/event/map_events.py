from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.connection import Connection
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.enum.world_enum import (
    TerrainTypeEnum,
    TriggerTypeEnum,
    ObjectTypeEnum,
    InteractionTypeEnum,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


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
    arrival_tick: Optional[WorldTick] = None


@dataclass(frozen=True)
class WorldObjectAddedEvent(BaseDomainEvent[WorldObjectId, str]):
    """オブジェクトが追加されたイベント"""
    object_id: WorldObjectId
    coordinate: Coordinate
    object_type: ObjectTypeEnum


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
class AreaTriggeredEvent(BaseDomainEvent[AreaTriggerId, str]):
    """エリアトリガーが発火したイベント"""
    trigger_id: AreaTriggerId
    spot_id: SpotId
    object_id: WorldObjectId
    trigger_type: TriggerTypeEnum


@dataclass(frozen=True)
class AreaEnteredEvent(BaseDomainEvent[AreaTriggerId, str]):
    """エリアに進入したイベント"""
    trigger_id: AreaTriggerId
    spot_id: SpotId
    object_id: WorldObjectId


@dataclass(frozen=True)
class AreaExitedEvent(BaseDomainEvent[AreaTriggerId, str]):
    """エリアから退出したイベント"""
    trigger_id: AreaTriggerId
    spot_id: SpotId
    object_id: WorldObjectId


@dataclass(frozen=True)
class WorldObjectInteractedEvent(BaseDomainEvent[WorldObjectId, str]):
    """オブジェクトとインタラクションしたイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    interaction_type: InteractionTypeEnum
    data: Dict[str, Any]


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


@dataclass(frozen=True)
class LocationEnteredEvent(BaseDomainEvent[LocationAreaId, str]):
    """ロケーションエリアに進入したイベント"""
    location_id: LocationAreaId
    spot_id: SpotId
    object_id: WorldObjectId
    name: str
    description: str


@dataclass(frozen=True)
class LocationExitedEvent(BaseDomainEvent[LocationAreaId, str]):
    """ロケーションエリアから退出したイベント"""
    location_id: LocationAreaId
    spot_id: SpotId
    object_id: WorldObjectId


@dataclass(frozen=True)
class GatewayTriggeredEvent(BaseDomainEvent[GatewayId, str]):
    """ゲートウェイ（出口）を通過したイベント"""
    gateway_id: GatewayId
    spot_id: SpotId
    object_id: WorldObjectId
    target_spot_id: SpotId
    landing_coordinate: Coordinate


@dataclass(frozen=True)
class ResourceHarvestedEvent(BaseDomainEvent[WorldObjectId, str]):
    """資源を採集・採掘したイベント"""
    object_id: WorldObjectId
    actor_id: WorldObjectId
    loot_table_id: str
    obtained_items: List[dict] # {"item_spec_id": str, "quantity": int}

    @classmethod
    def create(
        cls,
        aggregate_id: WorldObjectId,
        aggregate_type: str,
        object_id: WorldObjectId,
        actor_id: WorldObjectId,
        loot_table_id: str,
        obtained_items: List[dict]
    ) -> "ResourceHarvestedEvent":
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            object_id=object_id,
            actor_id=actor_id,
            loot_table_id=loot_table_id,
            obtained_items=obtained_items
        )


@dataclass(frozen=True)
class ItemStoredInChestEvent(BaseDomainEvent[SpotId, str]):
    """チェストにアイテムを収納したイベント（集約: PhysicalMap）"""
    spot_id: SpotId
    chest_id: WorldObjectId
    actor_id: WorldObjectId
    item_instance_id: ItemInstanceId
    player_id_value: int


@dataclass(frozen=True)
class ItemTakenFromChestEvent(BaseDomainEvent[SpotId, str]):
    """チェストからアイテムを取得したイベント（集約: PhysicalMap）"""
    spot_id: SpotId
    chest_id: WorldObjectId
    actor_id: WorldObjectId
    item_instance_id: ItemInstanceId
    player_id_value: int
