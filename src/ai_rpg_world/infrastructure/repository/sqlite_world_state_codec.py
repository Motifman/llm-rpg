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


def _pad_component_parent_row(values: tuple[Any, ...]) -> tuple[Any, ...]:
    expected_length = 46
    if len(values) > expected_length:
        raise ValueError(
            f"component parent row too long: expected <= {expected_length}, got {len(values)}"
        )
    if len(values) < expected_length:
        values = values + (None,) * (expected_length - len(values))
    return values


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


def component_to_record_storage(
    component: WorldObjectComponent | None,
) -> tuple[
    tuple[Any, ...],
    list[str],
    list[int],
    list[tuple[str, str, Any]],
    list[Coordinate],
    list[MonsterSkillInfo],
    list[str],
    list[str],
]:
    empty = _pad_component_parent_row((
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
        None,
        None,
        None,
        None,
        None,
    ))
    if component is None:
        return (empty, [], [], [], [], [], [], [])

    if isinstance(component, PlaceableComponent):
        trigger = component.get_trigger_on_step()
        trigger_values = (
            (None, None, None, None, None, None)
            if trigger is None
            else trigger_to_record_storage(trigger)
        )
        return (
            _pad_component_parent_row((
                "placeable",
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
                1 if isinstance(component._inner, ChestComponent) and component._inner.is_open else 0 if isinstance(component._inner, ChestComponent) else None,
                1 if isinstance(component._inner, DoorComponent) and component._inner.is_open else 0 if isinstance(component._inner, DoorComponent) else None,
                1 if isinstance(component._inner, DoorComponent) and component._inner.is_locked else 0 if isinstance(component._inner, DoorComponent) else None,
                None,
                None,
                None,
                int(component.item_spec_id),
                component._inner.get_type_name(),
                *trigger_values,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )),
            [],
            [int(item_id) for item_id in component._inner.item_ids] if isinstance(component._inner, ChestComponent) else [],
            [],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, AutonomousBehaviorComponent):
        aggro = component.aggro_memory_policy
        return (
            _pad_component_parent_row((
                "autonomous_actor",
                component.direction.value,
                component.capability.speed_modifier,
                None if component.player_id is None else int(component.player_id),
                1 if component.is_npc else 0,
                component.fov_angle,
                component.race,
                component.faction,
                None if component.pack_id is None else component.pack_id.value,
                component.vision_range,
                None if component.initial_position is None else component.initial_position.x,
                None if component.initial_position is None else component.initial_position.y,
                None if component.initial_position is None else component.initial_position.z,
                component.random_move_chance,
                component.behavior_strategy_type,
                1 if component.is_pack_leader else 0,
                component.ecology_type.value,
                component.ambush_chase_range,
                component.territory_radius,
                None if aggro is None else aggro.forget_after_ticks,
                None if aggro is None else (1 if aggro.revenge_never_forget else 0),
                component.active_time.value,
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
                None,
                None,
            )),
            [cap.value for cap in sorted(component.capability.capabilities, key=lambda cap: cap.value)],
            [],
            [],
            list(component.patrol_points),
            list(component.available_skills),
            sorted(component.threat_races),
            sorted(component.prey_races),
        )
    if isinstance(component, ActorComponent):
        return (
            _pad_component_parent_row((
                "actor",
                component.direction.value,
                component.capability.speed_modifier,
                None if component.player_id is None else int(component.player_id),
                1 if component.is_npc else 0,
                component.fov_angle,
                component.race,
                component.faction,
                None if component.pack_id is None else component.pack_id.value,
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
                None,
                None,
                None,
                None,
                None,
                None,
            )),
            [cap.value for cap in sorted(component.capability.capabilities, key=lambda cap: cap.value)],
            [],
            [],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, ChestComponent):
        return (
            _pad_component_parent_row((
                "chest",
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
                1 if component.is_open else 0,
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
                None,
                None,
                None,
            )),
            [],
            [int(item_id) for item_id in component.item_ids],
            [],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, DoorComponent):
        return (
            _pad_component_parent_row((
                "door",
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
                None,
                1 if component.is_open else 0,
                1 if component.is_locked else 0,
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
                None,
            )),
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, GroundItemComponent):
        return (
            _pad_component_parent_row((
                "ground_item",
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
                None,
                None,
                None,
                int(component.item_instance_id),
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
            )),
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, InteractableComponent):
        return (
            _pad_component_parent_row((
                "interactable",
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
                None,
                None,
                None,
                None,
                component.interaction_type.value,
                component.interaction_duration,
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
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )),
            [],
            [],
            [_encode_interaction_data(key, value) for key, value in component.interaction_data.items()],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, HarvestableComponent):
        return (
            _pad_component_parent_row((
                "harvestable",
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
                None,
                None,
                None,
                int(component.loot_table_id),
                component._max_quantity,
                component._current_quantity,
                component._respawn_interval,
                component._last_update_tick.value,
                component.required_tool_category,
                component.harvest_duration,
                component.stamina_cost,
                None if component.current_actor_id is None else int(component.current_actor_id),
                None if component.harvest_finish_tick is None else component.harvest_finish_tick.value,
            )),
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
    if isinstance(component, StaticPlaceableInnerComponent):
        return (
            _pad_component_parent_row((
                "static",
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
                None,
                None,
                None,
            )),
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
    raise ValueError(f"Unsupported component type: {type(component).__name__}")


def row_to_component(
    row: object,
    *,
    capability_rows: list[object],
    chest_item_rows: list[object],
    interaction_data_rows: list[object],
    patrol_rows: list[object],
    available_skill_rows: list[object],
    threat_race_rows: list[object],
    prey_race_rows: list[object],
) -> WorldObjectComponent | None:
    component_type = row["component_type"]
    if component_type is None:
        return None
    component_type = str(component_type)
    capability = MovementCapability(
        capabilities=frozenset(
            MovementCapabilityEnum(str(capability_row["capability"]))
            for capability_row in capability_rows
        ),
        speed_modifier=1.0 if row["actor_speed_modifier"] is None else float(row["actor_speed_modifier"]),
    )
    if component_type == "chest":
        return ChestComponent(
            is_open=bool(row["chest_is_open"]),
            item_ids=[ItemInstanceId(int(item_row["item_instance_id"])) for item_row in chest_item_rows],
        )
    if component_type == "door":
        return DoorComponent(
            is_open=bool(row["door_is_open"]),
            is_locked=bool(row["door_is_locked"]),
        )
    if component_type == "ground_item":
        return GroundItemComponent(ItemInstanceId(int(row["ground_item_instance_id"])))
    if component_type == "static":
        return StaticPlaceableInnerComponent()
    if component_type == "placeable":
        inner_type = str(row["placeable_inner_type"])
        if inner_type == "chest":
            inner: WorldObjectComponent = ChestComponent(
                is_open=bool(row["chest_is_open"]),
                item_ids=[ItemInstanceId(int(item_row["item_instance_id"])) for item_row in chest_item_rows],
            )
        elif inner_type == "door":
            inner = DoorComponent(
                is_open=bool(row["door_is_open"]),
                is_locked=bool(row["door_is_locked"]),
            )
        else:
            inner = StaticPlaceableInnerComponent()
        trigger = None
        if row["placeable_trigger_type"] is not None:
            trigger = row_to_trigger(row, prefix="placeable_trigger_")
        return PlaceableComponent(
            item_spec_id=ItemSpecId(int(row["placeable_item_spec_id"])),
            inner=inner,
            trigger_on_step=trigger,
        )
    if component_type == "actor":
        return ActorComponent(
            direction=DirectionEnum(str(row["actor_direction"])),
            capability=capability,
            player_id=None if row["actor_player_id"] is None else PlayerId(int(row["actor_player_id"])),
            is_npc=bool(row["actor_is_npc"]),
            fov_angle=float(row["actor_fov_angle"]),
            race=str(row["actor_race"]),
            faction=str(row["actor_faction"]),
            pack_id=None if row["actor_pack_id"] is None else PackId.create(str(row["actor_pack_id"])),
        )
    if component_type == "interactable":
        return InteractableComponent(
            interaction_type=InteractionTypeEnum(str(row["interactable_type"])),
            data={str(data_row["data_key"]): _decode_interaction_data(data_row) for data_row in interaction_data_rows},
            duration=int(row["interactable_duration"]),
        )
    if component_type == "autonomous_actor":
        aggro_policy = None
        if row["autonomous_aggro_forget_after_ticks"] is not None or row["autonomous_aggro_revenge_never_forget"] is not None:
            aggro_policy = AggroMemoryPolicy(
                forget_after_ticks=None if row["autonomous_aggro_forget_after_ticks"] is None else int(row["autonomous_aggro_forget_after_ticks"]),
                revenge_never_forget=bool(row["autonomous_aggro_revenge_never_forget"]),
            )
        return AutonomousBehaviorComponent(
            direction=DirectionEnum(str(row["actor_direction"])),
            capability=capability,
            player_id=None if row["actor_player_id"] is None else PlayerId(int(row["actor_player_id"])),
            is_npc=bool(row["actor_is_npc"]),
            vision_range=int(row["autonomous_vision_range"]),
            fov_angle=float(row["actor_fov_angle"]),
            patrol_points=[Coordinate(int(p["x"]), int(p["y"]), int(p["z"])) for p in patrol_rows],
            race=str(row["actor_race"]),
            faction=str(row["actor_faction"]),
            initial_position=None if row["autonomous_initial_x"] is None else Coordinate(int(row["autonomous_initial_x"]), int(row["autonomous_initial_y"]), int(row["autonomous_initial_z"])),
            random_move_chance=float(row["autonomous_random_move_chance"]),
            available_skills=[
                MonsterSkillInfo(
                    slot_index=int(skill_row["slot_index"]),
                    range=int(skill_row["range"]),
                    mp_cost=int(skill_row["mp_cost"]),
                )
                for skill_row in available_skill_rows
            ],
            behavior_strategy_type=str(row["autonomous_behavior_strategy_type"]),
            pack_id=None if row["actor_pack_id"] is None else PackId.create(str(row["actor_pack_id"])),
            is_pack_leader=bool(row["autonomous_is_pack_leader"]),
            ecology_type=EcologyTypeEnum(str(row["autonomous_ecology_type"])),
            ambush_chase_range=None if row["autonomous_ambush_chase_range"] is None else int(row["autonomous_ambush_chase_range"]),
            territory_radius=None if row["autonomous_territory_radius"] is None else int(row["autonomous_territory_radius"]),
            aggro_memory_policy=aggro_policy,
            active_time=ActiveTimeType(str(row["autonomous_active_time"])),
            threat_races=frozenset(str(race_row["race"]) for race_row in threat_race_rows),
            prey_races=frozenset(str(race_row["race"]) for race_row in prey_race_rows),
        )
    if component_type == "harvestable":
        component = HarvestableComponent(
            loot_table_id=LootTableId(int(row["harvest_loot_table_id"])),
            max_quantity=int(row["harvest_max_quantity"]),
            respawn_interval=int(row["harvest_respawn_interval"]),
            initial_quantity=int(row["harvest_current_quantity"]),
            last_harvest_tick=WorldTick(int(row["harvest_last_update_tick"])),
            required_tool_category=row["harvest_required_tool_category"],
            harvest_duration=int(row["harvest_duration"]),
            stamina_cost=int(row["harvest_stamina_cost"]),
        )
        component._current_actor_id = None if row["harvest_current_actor_id"] is None else WorldObjectId(int(row["harvest_current_actor_id"]))
        component._harvest_finish_tick = None if row["harvest_finish_tick"] is None else WorldTick(int(row["harvest_finish_tick"]))
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
    capability_rows: list[object],
    chest_item_rows: list[object],
    interaction_data_rows: list[object],
    patrol_rows: list[object],
    available_skill_rows: list[object],
    threat_race_rows: list[object],
    prey_race_rows: list[object],
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
    capability_rows_by_object = _group_rows_by_object_id(capability_rows)
    chest_item_rows_by_object = _group_rows_by_object_id(chest_item_rows)
    interaction_data_rows_by_object = _group_rows_by_object_id(interaction_data_rows)
    patrol_rows_by_object = _group_rows_by_object_id(patrol_rows)
    available_skill_rows_by_object = _group_rows_by_object_id(available_skill_rows)
    threat_race_rows_by_object = _group_rows_by_object_id(threat_race_rows)
    prey_race_rows_by_object = _group_rows_by_object_id(prey_race_rows)
    objects = [
        _build_world_object(
            row=object_row,
            capability_rows=capability_rows_by_object.get(int(object_row["world_object_id"]), []),
            chest_item_rows=chest_item_rows_by_object.get(int(object_row["world_object_id"]), []),
            interaction_data_rows=interaction_data_rows_by_object.get(int(object_row["world_object_id"]), []),
            patrol_rows=patrol_rows_by_object.get(int(object_row["world_object_id"]), []),
            available_skill_rows=available_skill_rows_by_object.get(int(object_row["world_object_id"]), []),
            threat_race_rows=threat_race_rows_by_object.get(int(object_row["world_object_id"]), []),
            prey_race_rows=prey_race_rows_by_object.get(int(object_row["world_object_id"]), []),
        )
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


def _build_world_object(
    *,
    row: object,
    capability_rows: list[object],
    chest_item_rows: list[object],
    interaction_data_rows: list[object],
    patrol_rows: list[object],
    available_skill_rows: list[object],
    threat_race_rows: list[object],
    prey_race_rows: list[object],
) -> WorldObject:
    component = row_to_component(
        row,
        capability_rows=capability_rows,
        chest_item_rows=chest_item_rows,
        interaction_data_rows=interaction_data_rows,
        patrol_rows=patrol_rows,
        available_skill_rows=available_skill_rows,
        threat_race_rows=threat_race_rows,
        prey_race_rows=prey_race_rows,
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


def _group_rows_by_object_id(rows: list[object]) -> dict[int, list[object]]:
    grouped: dict[int, list[object]] = {}
    for row in rows:
        grouped.setdefault(int(row["world_object_id"]), []).append(row)
    return grouped


def _encode_interaction_data(key: str, value: Any) -> tuple[str, str, Any]:
    if isinstance(value, bool):
        return (key, "bool", int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return (key, "int", value)
    if isinstance(value, float):
        return (key, "float", value)
    if value is None:
        return (key, "null", None)
    return (key, "text", str(value))


def _decode_interaction_data(row: object) -> Any:
    value_type = str(row["value_type"])
    if value_type == "bool":
        return bool(row["value_boolean"])
    if value_type == "int":
        return int(row["value_integer"])
    if value_type == "float":
        return float(row["value_real"])
    if value_type == "null":
        return None
    return "" if row["value_text"] is None else str(row["value_text"])


__all__ = [
    "area_to_storage",
    "area_to_record_storage",
    "build_physical_map",
    "component_to_record_storage",
    "coordinate_to_payload",
    "payload_to_coordinate",
    "row_to_area",
    "row_to_component",
    "row_to_trigger",
    "storage_to_area",
    "storage_to_trigger",
    "trigger_to_storage",
    "trigger_to_record_storage",
]
