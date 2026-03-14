"""MapTriggerEngine: エリア・ロケーション・ゲートウェイ・オブジェクト踏んだら発火のトリガー判定を行うドメインサービス。

リポジトリに依存せず、aggregate から渡されたデータのみで判定を行う。
発行すべきイベントのリストを返し、aggregate が add_event する責務を持つ。
"""

from typing import Dict, List, Optional, Tuple

from ai_rpg_world.domain.world.entity.map_trigger import MapTrigger
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.event.map_events import (
    AreaEnteredEvent,
    AreaExitedEvent,
    AreaTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    GatewayTriggeredEvent,
    ObjectTriggeredEvent,
)


class MapTriggerEngine:
    """
    AreaTrigger / LocationArea / Gateway / オブジェクト踏んだら発火のトリガー判定を行うドメインサービス。
    リポジトリ非依存。発行すべきイベントを返す。
    """

    @staticmethod
    def compute_area_trigger_events(
        object_id: WorldObjectId,
        old_coordinate: Optional[Coordinate],
        new_coordinate: Coordinate,
        area_triggers: Dict[AreaTriggerId, AreaTrigger],
        location_areas: Dict[LocationAreaId, LocationArea],
        gateways: Dict[GatewayId, Gateway],
        objects: Dict[WorldObjectId, WorldObject],
        spot_id: SpotId,
        current_tick: Optional[WorldTick] = None,
    ) -> List[BaseDomainEvent]:
        """
        進入・退出・滞在に応じて発行すべきイベントを算出する。
        AreaTrigger, LocationArea, Gateway の判定を行う。
        """
        events: List[BaseDomainEvent] = []

        # 1. AreaTrigger の判定
        for trigger in area_triggers.values():
            was_in = trigger.contains(old_coordinate) if old_coordinate else False
            is_in = trigger.contains(new_coordinate)

            if not was_in and is_in:
                events.append(
                    AreaEnteredEvent.create(
                        aggregate_id=trigger.trigger_id,
                        aggregate_type="AreaTrigger",
                        trigger_id=trigger.trigger_id,
                        spot_id=spot_id,
                        object_id=object_id,
                    )
                )
                events.append(
                    AreaTriggeredEvent.create(
                        aggregate_id=trigger.trigger_id,
                        aggregate_type="AreaTrigger",
                        trigger_id=trigger.trigger_id,
                        spot_id=spot_id,
                        object_id=object_id,
                        trigger_type=trigger.trigger.get_trigger_type(),
                    )
                )
            elif was_in and not is_in:
                events.append(
                    AreaExitedEvent.create(
                        aggregate_id=trigger.trigger_id,
                        aggregate_type="AreaTrigger",
                        trigger_id=trigger.trigger_id,
                        spot_id=spot_id,
                        object_id=object_id,
                    )
                )
            elif was_in and is_in:
                events.append(
                    AreaTriggeredEvent.create(
                        aggregate_id=trigger.trigger_id,
                        aggregate_type="AreaTrigger",
                        trigger_id=trigger.trigger_id,
                        spot_id=spot_id,
                        object_id=object_id,
                        trigger_type=trigger.trigger.get_trigger_type(),
                    )
                )

        # 2. LocationArea の判定
        obj = objects.get(object_id)
        player_id_value = obj.player_id.value if (obj and obj.player_id) else None

        for loc in location_areas.values():
            was_in = loc.contains(old_coordinate) if old_coordinate else False
            is_in = loc.contains(new_coordinate)

            if not was_in and is_in:
                events.append(
                    LocationEnteredEvent.create(
                        aggregate_id=loc.location_id,
                        aggregate_type="LocationArea",
                        location_id=loc.location_id,
                        spot_id=spot_id,
                        object_id=object_id,
                        name=loc.name,
                        description=loc.description,
                        player_id_value=player_id_value,
                    )
                )
            elif was_in and not is_in:
                events.append(
                    LocationExitedEvent.create(
                        aggregate_id=loc.location_id,
                        aggregate_type="LocationArea",
                        location_id=loc.location_id,
                        spot_id=spot_id,
                        object_id=object_id,
                    )
                )

        # 3. Gateway の判定
        for gateway in gateways.values():
            was_in = gateway.contains(old_coordinate) if old_coordinate else False
            is_in = gateway.contains(new_coordinate)

            if not was_in and is_in:
                events.append(
                    GatewayTriggeredEvent.create(
                        aggregate_id=gateway.gateway_id,
                        aggregate_type="Gateway",
                        gateway_id=gateway.gateway_id,
                        spot_id=spot_id,
                        object_id=object_id,
                        target_spot_id=gateway.target_spot_id,
                        landing_coordinate=gateway.landing_coordinate,
                        player_id_value=player_id_value,
                        occurred_tick=current_tick,
                    )
                )

        return events

    @staticmethod
    def compute_object_trigger_events(
        actor_id: WorldObjectId,
        new_coordinate: Coordinate,
        objects: Dict[WorldObjectId, WorldObject],
        object_positions: Dict[Coordinate, List[WorldObjectId]],
        spot_id: SpotId,
    ) -> List[BaseDomainEvent]:
        """
        指定座標にあるオブジェクトの get_trigger_on_step に応じたイベントを算出する。
        """
        events: List[BaseDomainEvent] = []

        if new_coordinate not in object_positions:
            return events

        for obj_id in object_positions[new_coordinate]:
            if obj_id == actor_id:
                continue
            obj = objects.get(obj_id)
            if not obj or not obj.component:
                continue
            trigger = obj.component.get_trigger_on_step()
            if trigger is not None:
                events.append(
                    ObjectTriggeredEvent.create(
                        aggregate_id=obj_id,
                        aggregate_type="WorldObject",
                        object_id=obj_id,
                        spot_id=spot_id,
                        actor_id=actor_id,
                        trigger_type=trigger.get_trigger_type(),
                    )
                )

        return events

    @staticmethod
    def compute_trigger_activation_at_coordinate(
        coordinate: Coordinate,
        object_id: Optional[WorldObjectId],
        area_triggers: Dict[AreaTriggerId, AreaTrigger],
        spot_id: SpotId,
    ) -> Tuple[Optional[MapTrigger], List[BaseDomainEvent]]:
        """
        指定座標を含む最初のアクティブなエリアトリガーを検出し、
        object_id が指定されていれば AreaTriggeredEvent を返す。
        戻り値: (見つかった MapTrigger, 発行すべきイベントリスト)
        """
        for trigger in area_triggers.values():
            if trigger.contains(coordinate):
                events: List[BaseDomainEvent] = []
                if object_id is not None:
                    events.append(
                        AreaTriggeredEvent.create(
                            aggregate_id=trigger.trigger_id,
                            aggregate_type="AreaTrigger",
                            trigger_id=trigger.trigger_id,
                            spot_id=spot_id,
                            object_id=object_id,
                            trigger_type=trigger.trigger.get_trigger_type(),
                        )
                    )
                return (trigger.trigger, events)
        return (None, [])
