"""Helpers for normalized physical-map SQLite persistence."""

from __future__ import annotations

import json
from typing import Any

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.monster.enum.monster_enum import ActiveTimeType, EcologyTypeEnum
from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.entity.map_trigger import DamageTrigger, MapTrigger, WarpTrigger
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AggroMemoryPolicy,
    AutonomousBehaviorComponent,
    ChestComponent,
    DoorComponent,
    GroundItemComponent,
    HarvestableComponent,
    InteractableComponent,
    PlaceableComponent,
    StaticPlaceableInnerComponent,
    WorldObjectComponent,
)
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import (
    DirectionEnum,
    EnvironmentTypeEnum,
    InteractionTypeEnum,
    MovementCapabilityEnum,
    ObjectTypeEnum,
    SpotTraitEnum,
    TerrainTypeEnum,
    TriggerTypeEnum,
)
from ai_rpg_world.domain.world.value_object.area import Area, CircleArea, PointArea, RectArea
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.movement_cost import MovementCost
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def coordinate_to_payload(coordinate: Coordinate | None) -> dict[str, int] | None:
    if coordinate is None:
        return None
    return {"x": coordinate.x, "y": coordinate.y, "z": coordinate.z}


def payload_to_coordinate(payload: dict[str, Any] | None) -> Coordinate | None:
    if payload is None:
        return None
    return Coordinate(int(payload["x"]), int(payload["y"]), int(payload.get("z", 0)))


def area_to_storage(area: Area) -> tuple[str, str]:
    if isinstance(area, PointArea):
        payload = {"coordinate": coordinate_to_payload(area.coordinate)}
        return ("point", json.dumps(payload, ensure_ascii=True, sort_keys=True))
    if isinstance(area, RectArea):
        payload = {
            "min_x": area.min_x,
            "max_x": area.max_x,
            "min_y": area.min_y,
            "max_y": area.max_y,
            "min_z": area.min_z,
            "max_z": area.max_z,
        }
        return ("rect", json.dumps(payload, ensure_ascii=True, sort_keys=True))
    if isinstance(area, CircleArea):
        payload = {
            "center": coordinate_to_payload(area.center),
            "radius": area.radius,
        }
        return ("circle", json.dumps(payload, ensure_ascii=True, sort_keys=True))
    raise ValueError(f"Unsupported area type: {type(area).__name__}")


def storage_to_area(area_kind: str, payload_json: str) -> Area:
    payload = json.loads(payload_json)
    if area_kind == "point":
        coordinate = payload_to_coordinate(payload["coordinate"])
        if coordinate is None:
            raise ValueError("point area requires coordinate")
        return PointArea(coordinate)
    if area_kind == "rect":
        return RectArea(
            min_x=int(payload["min_x"]),
            max_x=int(payload["max_x"]),
            min_y=int(payload["min_y"]),
            max_y=int(payload["max_y"]),
            min_z=int(payload["min_z"]),
            max_z=int(payload["max_z"]),
        )
    if area_kind == "circle":
        center = payload_to_coordinate(payload["center"])
        if center is None:
            raise ValueError("circle area requires center")
        return CircleArea(center=center, radius=int(payload["radius"]))
    raise ValueError(f"Unsupported area kind: {area_kind}")


def trigger_to_storage(trigger: MapTrigger) -> tuple[str, str]:
    payload = trigger.to_dict()
    trigger_type = payload.pop("type", trigger.get_trigger_type().value)
    return (str(trigger_type), json.dumps(payload, ensure_ascii=True, sort_keys=True))


def storage_to_trigger(trigger_type: str, payload_json: str) -> MapTrigger:
    payload = json.loads(payload_json)
    trigger_enum = TriggerTypeEnum(trigger_type)
    if trigger_enum is TriggerTypeEnum.WARP:
        target_coordinate = payload_to_coordinate(payload["target_coordinate"])
        if target_coordinate is None:
            raise ValueError("warp trigger requires target_coordinate")
        return WarpTrigger(
            target_spot_id=SpotId(int(payload["target_spot_id"])),
            target_coordinate=target_coordinate,
        )
    if trigger_enum is TriggerTypeEnum.DAMAGE:
        return DamageTrigger(damage=int(payload["damage"]))
    raise ValueError(f"Unsupported trigger type: {trigger_type}")


def area_to_record_storage(
    area: Area,
) -> tuple[
    str,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
]:
    if isinstance(area, PointArea):
        return (
            "point",
            area.coordinate.x,
            area.coordinate.y,
            area.coordinate.z,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    if isinstance(area, RectArea):
        return (
            "rect",
            None,
            None,
            None,
            area.min_x,
            area.max_x,
            area.min_y,
            area.max_y,
            area.min_z,
            area.max_z,
            None,
            None,
            None,
            None,
        )
    if isinstance(area, CircleArea):
        return (
            "circle",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            area.center.x,
            area.center.y,
            area.center.z,
            area.radius,
        )
    raise ValueError(f"Unsupported area type: {type(area).__name__}")


def row_to_area(row: object, *, prefix: str = "area_") -> Area:
    area_kind = str(row[f"{prefix}kind"])
    if area_kind == "point":
        return PointArea(
            Coordinate(
                int(row[f"{prefix}point_x"]),
                int(row[f"{prefix}point_y"]),
                int(row[f"{prefix}point_z"]),
            )
        )
    if area_kind == "rect":
        return RectArea(
            min_x=int(row[f"{prefix}rect_min_x"]),
            max_x=int(row[f"{prefix}rect_max_x"]),
            min_y=int(row[f"{prefix}rect_min_y"]),
            max_y=int(row[f"{prefix}rect_max_y"]),
            min_z=int(row[f"{prefix}rect_min_z"]),
            max_z=int(row[f"{prefix}rect_max_z"]),
        )
    if area_kind == "circle":
        return CircleArea(
            center=Coordinate(
                int(row[f"{prefix}circle_center_x"]),
                int(row[f"{prefix}circle_center_y"]),
                int(row[f"{prefix}circle_center_z"]),
            ),
            radius=int(row[f"{prefix}circle_radius"]),
        )
    raise ValueError(f"Unsupported area kind: {area_kind}")


def trigger_to_record_storage(
    trigger: MapTrigger,
) -> tuple[str, int | None, int | None, int | None, int | None, int | None]:
    if isinstance(trigger, WarpTrigger):
        return (
            TriggerTypeEnum.WARP.value,
            int(trigger.target_spot_id),
            trigger.target_coordinate.x,
            trigger.target_coordinate.y,
            trigger.target_coordinate.z,
            None,
        )
    if isinstance(trigger, DamageTrigger):
        return (
            TriggerTypeEnum.DAMAGE.value,
            None,
            None,
            None,
            None,
            int(trigger.damage),
        )
    raise ValueError(f"Unsupported trigger type: {type(trigger).__name__}")


def row_to_trigger(row: object, *, prefix: str = "trigger_") -> MapTrigger:
    trigger_type = str(row[f"{prefix}type"])
    if trigger_type == TriggerTypeEnum.WARP.value:
        return WarpTrigger(
            target_spot_id=SpotId(int(row[f"{prefix}warp_target_spot_id"])),
            target_coordinate=Coordinate(
                int(row[f"{prefix}warp_target_x"]),
                int(row[f"{prefix}warp_target_y"]),
                int(row[f"{prefix}warp_target_z"]),
            ),
        )
    if trigger_type == TriggerTypeEnum.DAMAGE.value:
        return DamageTrigger(damage=int(row[f"{prefix}damage"]))
    raise ValueError(f"Unsupported trigger type: {trigger_type}")


def component_to_storage(component: WorldObjectComponent | None) -> tuple[str | None, str | None]:
    if component is None:
        return (None, None)
    component_type = component.get_type_name()
    payload = _component_payload(component)
    return (
        component_type,
        json.dumps(payload, ensure_ascii=True, sort_keys=True),
    )


def storage_to_component(component_type: str | None, payload_json: str | None) -> WorldObjectComponent | None:
    if component_type is None:
        return None
    payload = {} if payload_json is None else json.loads(payload_json)
    if component_type == "chest":
        return ChestComponent(
            is_open=bool(payload.get("is_open", False)),
            item_ids=[ItemInstanceId(int(item_id)) for item_id in payload.get("item_ids", [])],
        )
    if component_type == "door":
        return DoorComponent(
            is_open=bool(payload.get("is_open", False)),
            is_locked=bool(payload.get("is_locked", False)),
        )
    if component_type == "ground_item":
        return GroundItemComponent(ItemInstanceId(int(payload["item_instance_id"])))
    if component_type == "static":
        return StaticPlaceableInnerComponent()
    if component_type.startswith("placeable("):
        inner_type = payload["inner_type"]
        inner_payload = json.dumps(payload.get("inner_payload", {}), ensure_ascii=True, sort_keys=True)
        inner = storage_to_component(inner_type, inner_payload)
        trigger_payload = payload.get("trigger_on_step")
        return PlaceableComponent(
            item_spec_id=ItemSpecId(int(payload["item_spec_id"])),
            inner=inner if inner is not None else StaticPlaceableInnerComponent(),
            trigger_on_step=(
                None
                if trigger_payload is None
                else storage_to_trigger(trigger_payload["type"], json.dumps(trigger_payload["payload"], ensure_ascii=True, sort_keys=True))
            ),
        )
    if component_type == "actor":
        return ActorComponent(
            direction=DirectionEnum(payload["direction"]),
            capability=_payload_to_movement_capability(payload["capability"]),
            player_id=None if payload.get("player_id") is None else PlayerId(int(payload["player_id"])),
            is_npc=bool(payload.get("is_npc", False)),
            fov_angle=float(payload.get("fov_angle", 360.0)),
            race=str(payload.get("race", "human")),
            faction=str(payload.get("faction", "neutral")),
            pack_id=None if payload.get("pack_id") is None else PackId.create(payload["pack_id"]),
        )
    if component_type == "interactable":
        return InteractableComponent(
            interaction_type=InteractionTypeEnum(payload["interaction_type"]),
            data=dict(payload.get("data", {})),
            duration=int(payload.get("duration", 1)),
        )
    if component_type == "autonomous_actor":
        available_skills = [
            MonsterSkillInfo(
                slot_index=int(skill["slot_index"]),
                range=int(skill["range"]),
                mp_cost=int(skill["mp_cost"]),
            )
            for skill in payload.get("available_skills", [])
        ]
        aggro_memory_policy = payload.get("aggro_memory_policy")
        return AutonomousBehaviorComponent(
            direction=DirectionEnum(payload["direction"]),
            capability=_payload_to_movement_capability(payload["capability"]),
            player_id=None if payload.get("player_id") is None else PlayerId(int(payload["player_id"])),
            is_npc=bool(payload.get("is_npc", True)),
            vision_range=int(payload.get("vision_range", 5)),
            fov_angle=float(payload.get("fov_angle", 90.0)),
            patrol_points=[
                payload_to_coordinate(point)
                for point in payload.get("patrol_points", [])
                if payload_to_coordinate(point) is not None
            ],
            race=str(payload.get("race", "monster")),
            faction=str(payload.get("faction", "enemy")),
            initial_position=payload_to_coordinate(payload.get("initial_position")),
            random_move_chance=float(payload.get("random_move_chance", 0.5)),
            available_skills=available_skills,
            behavior_strategy_type=str(payload.get("behavior_strategy_type", "default")),
            pack_id=None if payload.get("pack_id") is None else PackId.create(payload["pack_id"]),
            is_pack_leader=bool(payload.get("is_pack_leader", False)),
            ecology_type=EcologyTypeEnum(payload.get("ecology_type", EcologyTypeEnum.NORMAL.value)),
            ambush_chase_range=payload.get("ambush_chase_range"),
            territory_radius=payload.get("territory_radius"),
            aggro_memory_policy=(
                None
                if aggro_memory_policy is None
                else AggroMemoryPolicy(
                    forget_after_ticks=aggro_memory_policy.get("forget_after_ticks"),
                    revenge_never_forget=bool(aggro_memory_policy.get("revenge_never_forget", False)),
                )
            ),
            active_time=ActiveTimeType(payload.get("active_time", ActiveTimeType.ALWAYS.value)),
            threat_races=frozenset(str(race) for race in payload.get("threat_races", [])),
            prey_races=frozenset(str(race) for race in payload.get("prey_races", [])),
        )
    if component_type == "harvestable":
        component = HarvestableComponent(
            loot_table_id=LootTableId(int(payload["loot_table_id"])),
            max_quantity=int(payload["max_quantity"]),
            respawn_interval=int(payload["respawn_interval"]),
            initial_quantity=int(payload["current_quantity"]),
            last_harvest_tick=WorldTick(int(payload["last_update_tick"])),
            required_tool_category=payload.get("required_tool_category"),
            harvest_duration=int(payload.get("harvest_duration", 5)),
            stamina_cost=int(payload.get("stamina_cost", 10)),
        )
        current_actor_id = payload.get("current_actor_id")
        harvest_finish_tick = payload.get("harvest_finish_tick")
        component._current_actor_id = None if current_actor_id is None else WorldObjectId(int(current_actor_id))
        component._harvest_finish_tick = (
            None if harvest_finish_tick is None else WorldTick(int(harvest_finish_tick))
        )
        return component
    raise ValueError(f"Unsupported component type: {component_type}")


def build_physical_map(
    *,
    row: object,
    tile_rows: list[object],
    object_rows: list[object],
    area_trigger_rows: list[object],
    location_area_rows: list[object],
    gateway_rows: list[object],
    area_trait_rows: list[str],
) -> PhysicalMapAggregate:
    tiles = {
        Coordinate(int(tile_row["x"]), int(tile_row["y"]), int(tile_row["z"])): Tile(
            coordinate=Coordinate(int(tile_row["x"]), int(tile_row["y"]), int(tile_row["z"])),
            terrain_type=TerrainType(
                type=TerrainTypeEnum(tile_row["terrain_type"]),
                base_cost=MovementCost(float(tile_row["base_cost"])),
                required_capabilities=frozenset(
                    MovementCapabilityEnum(capability)
                    for capability in json.loads(str(tile_row["required_capabilities_json"]))
                ),
                is_opaque=bool(tile_row["is_opaque"]),
            ),
            is_walkable_override=(
                None
                if tile_row["is_walkable_override"] is None
                else bool(tile_row["is_walkable_override"])
            ),
        )
        for tile_row in tile_rows
    }
    objects = [
        _build_world_object(row=object_row)
        for object_row in object_rows
    ]
    area_triggers = [
        AreaTrigger(
            trigger_id=AreaTriggerId(int(trigger_row["trigger_id"])),
            area=row_to_area(trigger_row),
            trigger=row_to_trigger(trigger_row),
            name=str(trigger_row["name"]),
            is_active=bool(trigger_row["is_active"]),
        )
        for trigger_row in area_trigger_rows
    ]
    location_areas = [
        LocationArea(
            location_id=LocationAreaId(int(location_row["location_area_id"])),
            area=row_to_area(location_row),
            name=str(location_row["name"]),
            description=str(location_row["description"]),
            is_active=bool(location_row["is_active"]),
        )
        for location_row in location_area_rows
    ]
    gateways = [
        Gateway(
            gateway_id=GatewayId(int(gateway_row["gateway_id"])),
            name=str(gateway_row["name"]),
            area=row_to_area(gateway_row),
            target_spot_id=SpotId(int(gateway_row["target_spot_id"])),
            landing_coordinate=Coordinate(
                int(gateway_row["landing_x"]),
                int(gateway_row["landing_y"]),
                int(gateway_row["landing_z"]),
            ),
            is_active=bool(gateway_row["is_active"]),
        )
        for gateway_row in gateway_rows
    ]
    physical_map = PhysicalMapAggregate(
        spot_id=SpotId(int(row["spot_id"])),
        tiles=tiles,
        objects=objects,
        area_triggers=area_triggers,
        location_areas=location_areas,
        gateways=gateways,
        environment_type=EnvironmentTypeEnum(str(row["environment_type"])),
        area_traits=[SpotTraitEnum(value) for value in area_trait_rows],
    )
    physical_map.set_weather(
        WeatherState(
            weather_type=WeatherTypeEnum(str(row["weather_type"])),
            intensity=float(row["weather_intensity"]),
        )
    )
    physical_map.clear_events()
    return physical_map


def _component_payload(component: WorldObjectComponent) -> dict[str, Any]:
    if isinstance(component, PlaceableComponent):
        trigger_payload = None
        if component.get_trigger_on_step() is not None:
            trigger_type, trigger_json = trigger_to_storage(component.get_trigger_on_step())
            trigger_payload = {"type": trigger_type, "payload": json.loads(trigger_json)}
        return {
            "item_spec_id": int(component.item_spec_id),
            "inner_type": component._inner.get_type_name(),
            "inner_payload": _component_payload(component._inner),
            "trigger_on_step": trigger_payload,
        }
    if isinstance(component, ActorComponent) and not isinstance(component, AutonomousBehaviorComponent):
        return {
            "direction": component.direction.value,
            "capability": _movement_capability_to_payload(component.capability),
            "player_id": None if component.player_id is None else int(component.player_id),
            "is_npc": component.is_npc,
            "fov_angle": component.fov_angle,
            "race": component.race,
            "faction": component.faction,
            "pack_id": None if component.pack_id is None else component.pack_id.value,
        }
    if isinstance(component, AutonomousBehaviorComponent):
        return {
            "direction": component.direction.value,
            "capability": _movement_capability_to_payload(component.capability),
            "player_id": None if component.player_id is None else int(component.player_id),
            "is_npc": component.is_npc,
            "vision_range": component.vision_range,
            "fov_angle": component.fov_angle,
            "patrol_points": [coordinate_to_payload(point) for point in component.patrol_points],
            "race": component.race,
            "faction": component.faction,
            "initial_position": coordinate_to_payload(component.initial_position),
            "random_move_chance": component.random_move_chance,
            "available_skills": [
                {"slot_index": skill.slot_index, "range": skill.range, "mp_cost": skill.mp_cost}
                for skill in component.available_skills
            ],
            "behavior_strategy_type": component.behavior_strategy_type,
            "pack_id": None if component.pack_id is None else component.pack_id.value,
            "is_pack_leader": component.is_pack_leader,
            "ecology_type": component.ecology_type.value,
            "ambush_chase_range": component.ambush_chase_range,
            "territory_radius": component.territory_radius,
            "aggro_memory_policy": None
            if component.aggro_memory_policy is None
            else {
                "forget_after_ticks": component.aggro_memory_policy.forget_after_ticks,
                "revenge_never_forget": component.aggro_memory_policy.revenge_never_forget,
            },
            "active_time": component.active_time.value,
            "threat_races": sorted(component.threat_races),
            "prey_races": sorted(component.prey_races),
        }
    if isinstance(component, InteractableComponent):
        return {
            "interaction_type": component.interaction_type.value,
            "data": dict(component.interaction_data),
            "duration": component.interaction_duration,
        }
    if isinstance(component, HarvestableComponent):
        return {
            "loot_table_id": int(component.loot_table_id),
            "max_quantity": component._max_quantity,
            "current_quantity": component._current_quantity,
            "respawn_interval": component._respawn_interval,
            "last_update_tick": component._last_update_tick.value,
            "required_tool_category": component.required_tool_category,
            "harvest_duration": component.harvest_duration,
            "stamina_cost": component.stamina_cost,
            "current_actor_id": None if component.current_actor_id is None else int(component.current_actor_id),
            "harvest_finish_tick": (
                None if component.harvest_finish_tick is None else component.harvest_finish_tick.value
            ),
        }
    return component.to_dict()


def _build_world_object(*, row: object) -> WorldObject:
    component = storage_to_component(
        None if row["component_type"] is None else str(row["component_type"]),
        None if row["component_payload_json"] is None else str(row["component_payload_json"]),
    )
    return WorldObject(
        object_id=WorldObjectId(int(row["world_object_id"])),
        coordinate=Coordinate(int(row["x"]), int(row["y"]), int(row["z"])),
        object_type=ObjectTypeEnum(str(row["object_type"])),
        is_blocking=bool(row["is_blocking"]),
        is_blocking_sight=bool(row["is_blocking_sight"]),
        component=component,
        busy_until=None if row["busy_until_tick"] is None else WorldTick(int(row["busy_until_tick"])),
    )


def _movement_capability_to_payload(capability: MovementCapability) -> dict[str, Any]:
    return {
        "capabilities": sorted(cap.value for cap in capability.capabilities),
        "speed_modifier": capability.speed_modifier,
    }


def _payload_to_movement_capability(payload: dict[str, Any]) -> MovementCapability:
    return MovementCapability(
        capabilities=frozenset(MovementCapabilityEnum(value) for value in payload["capabilities"]),
        speed_modifier=float(payload["speed_modifier"]),
    )


__all__ = [
    "area_to_storage",
    "area_to_record_storage",
    "build_physical_map",
    "component_to_storage",
    "coordinate_to_payload",
    "payload_to_coordinate",
    "row_to_area",
    "row_to_trigger",
    "storage_to_area",
    "storage_to_component",
    "storage_to_trigger",
    "trigger_to_storage",
    "trigger_to_record_storage",
]
