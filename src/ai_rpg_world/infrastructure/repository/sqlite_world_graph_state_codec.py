"""スポットグラフ集約・スポット内部構造の JSON スナップショット（SQLite 用）。"""

from __future__ import annotations

import json
from dataclasses import replace
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
    SpotGraphConnectionRecord,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.passage_kind import PassageKindEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.infrastructure.repository.spot_graph_persistence_exceptions import (
    SpotGraphConnectionRecordInvariantError,
    UnsupportedSpotGraphAggregateSchemaError,
    UnsupportedSpotInteriorSchemaError,
)

E = TypeVar("E", bound=Enum)


def _enum_name(value: Enum) -> str:
    return value.name


def _parse_enum(enum_cls: Type[E], name: str) -> E:
    return enum_cls[name]


AGGREGATE_SCHEMA_VERSION = 2
INTERIOR_SCHEMA_VERSION = 1


def spot_graph_aggregate_to_json_dict(graph: SpotGraphAggregate) -> dict[str, Any]:
    """SpotGraphAggregate を JSON 互換 dict に変換する（ノードの interior は含めない）。"""
    connection_records = _encode_connection_records(graph.iter_connection_records())
    entity_spot = {str(int(eid)): int(sid.value) for eid, sid in graph.entity_spot_mapping().items()}
    spots = sorted(
        (_spot_node_to_dict(replace(n, interior=None)) for n in graph.iter_spot_nodes()),
        key=lambda d: int(d["spot_id"]),
    )
    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "graph_id": int(graph.graph_id.value),
        "spots": spots,
        "connection_records": connection_records,
        "entity_spot": entity_spot,
    }


def spot_graph_aggregate_from_json_dict(payload: dict[str, Any]) -> SpotGraphAggregate:
    """JSON dict から SpotGraphAggregate を復元する。"""
    version = int(payload["schema_version"])
    if version not in (1, AGGREGATE_SCHEMA_VERSION):
        raise UnsupportedSpotGraphAggregateSchemaError(
            f"Unsupported spot graph aggregate schema: {version}"
        )

    graph_id = SpotGraphId.create(int(payload["graph_id"]))
    graph = SpotGraphAggregate.empty(graph_id)

    for spot_payload in payload["spots"]:
        graph.add_spot(_spot_node_from_dict(spot_payload))

    for record in payload["connection_records"]:
        if record["kind"] == "oneway":
            conn = _spot_connection_from_dict(record["conn"])
            graph.add_connection(conn)
        elif record["kind"] == "bidirectional":
            forward_blob = record.get("conn", record.get("forward"))
            if forward_blob is None:
                raise SpotGraphConnectionRecordInvariantError(
                    "Bidirectional connection record must include conn or forward"
                )
            if record.get("reverse_connection_id") is None:
                raise SpotGraphConnectionRecordInvariantError(
                    "Bidirectional connection record must include reverse_connection_id"
                )
            forward = _spot_connection_from_dict(forward_blob)
            rev_id = ConnectionId.create(int(record["reverse_connection_id"]))
            graph.add_connection(forward, reverse_connection_id=rev_id)
        else:
            raise SpotGraphConnectionRecordInvariantError(
                f"Unknown connection record kind: {record.get('kind')}"
            )

    for entity_key, spot_int in payload["entity_spot"].items():
        graph.place_entity(EntityId.create(int(entity_key)), SpotId.create(int(spot_int)))

    graph.clear_events()
    return graph


def spot_interior_to_json_dict(interior: SpotInterior) -> dict[str, Any]:
    return {
        "schema_version": INTERIOR_SCHEMA_VERSION,
        "sub_locations": [_sub_location_to_dict(s) for s in interior.sub_locations],
        "objects": [_spot_object_to_dict(o) for o in interior.objects],
        "ground_items": [_ground_item_to_dict(g) for g in interior.ground_items],
        "discoverable_items": [_discoverable_item_to_dict(d) for d in interior.discoverable_items],
    }


def spot_interior_from_json_dict(payload: dict[str, Any]) -> SpotInterior:
    version = int(payload["schema_version"])
    if version != INTERIOR_SCHEMA_VERSION:
        raise UnsupportedSpotInteriorSchemaError(
            f"Unsupported spot interior schema: {version}"
        )
    return SpotInterior(
        sub_locations=tuple(_sub_location_from_dict(x) for x in payload["sub_locations"]),
        objects=tuple(_spot_object_from_dict(x) for x in payload["objects"]),
        ground_items=tuple(_ground_item_from_dict(x) for x in payload["ground_items"]),
        discoverable_items=tuple(_discoverable_item_from_dict(x) for x in payload["discoverable_items"]),
    )


def dumps_spot_graph_aggregate(graph: SpotGraphAggregate) -> str:
    return json.dumps(spot_graph_aggregate_to_json_dict(graph), ensure_ascii=True, sort_keys=True)


def loads_spot_graph_aggregate(blob: str) -> SpotGraphAggregate:
    return spot_graph_aggregate_from_json_dict(json.loads(blob))


def dumps_spot_interior(interior: SpotInterior) -> str:
    return json.dumps(spot_interior_to_json_dict(interior), ensure_ascii=True, sort_keys=True)


def loads_spot_interior(blob: str) -> SpotInterior:
    return spot_interior_from_json_dict(json.loads(blob))


def _encode_connection_records(
    connection_records: Tuple[SpotGraphConnectionRecord, ...],
) -> List[dict[str, Any]]:
    if not connection_records:
        return []
    out: List[dict[str, Any]] = []
    for record in connection_records:
        conn = record.connection
        if not record.is_bidirectional:
            out.append({"kind": "oneway", "conn": _spot_connection_to_dict(conn)})
            continue
        if record.reverse_connection_id is None:
            raise SpotGraphConnectionRecordInvariantError(
                f"Bidirectional record missing reverse ID for connection {conn.connection_id}"
            )
        out.append(
            {
                "kind": "bidirectional",
                "conn": _spot_connection_to_dict(conn),
                "reverse_connection_id": int(record.reverse_connection_id.value),
            }
        )
    out.sort(
        key=lambda r: (
            r["kind"],
            r["conn"]["connection_id"],
        )
    )
    return out


def _spot_node_to_dict(node: SpotNode) -> dict[str, Any]:
    d: dict[str, Any] = {
        "spot_id": int(node.spot_id.value),
        "name": node.name,
        "description": node.description,
        "category": _enum_name(node.category),
        "parent_id": int(node.parent_id.value) if node.parent_id is not None else None,
    }
    if node.atmosphere is not None:
        d["atmosphere"] = _spot_atmosphere_to_dict(node.atmosphere)
    return d


def _spot_node_from_dict(d: dict[str, Any]) -> SpotNode:
    parent = SpotId.create(int(d["parent_id"])) if d.get("parent_id") is not None else None
    atmosphere = _spot_atmosphere_from_dict(d["atmosphere"]) if d.get("atmosphere") else None
    return SpotNode(
        spot_id=SpotId.create(int(d["spot_id"])),
        name=d["name"],
        description=d["description"],
        category=_parse_enum(SpotCategoryEnum, d["category"]),
        parent_id=parent,
        interior=None,
        atmosphere=atmosphere,
    )


def _spot_atmosphere_to_dict(a: SpotAtmosphere) -> dict[str, Any]:
    return {
        "lighting": _enum_name(a.lighting),
        "sound_ambient": a.sound_ambient,
        "temperature": _enum_name(a.temperature),
        "smell": a.smell,
    }


def _spot_atmosphere_from_dict(d: dict[str, Any]) -> SpotAtmosphere:
    return SpotAtmosphere(
        lighting=_parse_enum(LightingEnum, d["lighting"]),
        sound_ambient=d.get("sound_ambient"),
        temperature=_parse_enum(TemperatureEnum, d.get("temperature", "NORMAL")),
        smell=d.get("smell"),
    )


def _spot_connection_to_dict(conn: SpotConnection) -> dict[str, Any]:
    return {
        "connection_id": int(conn.connection_id.value),
        "from_spot_id": int(conn.from_spot_id.value),
        "to_spot_id": int(conn.to_spot_id.value),
        "name": conn.name,
        "description": conn.description,
        "travel_ticks": conn.travel_ticks,
        "is_bidirectional": conn.is_bidirectional,
        "passage_conditions": [_passage_condition_to_dict(p) for p in conn.passage_conditions],
        "passage": _passage_to_dict(conn.passage),
    }


def _spot_connection_from_dict(d: dict[str, Any]) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(int(d["connection_id"])),
        from_spot_id=SpotId.create(int(d["from_spot_id"])),
        to_spot_id=SpotId.create(int(d["to_spot_id"])),
        name=d["name"],
        description=d["description"],
        travel_ticks=int(d["travel_ticks"]),
        is_bidirectional=bool(d["is_bidirectional"]),
        passage_conditions=[_passage_condition_from_dict(x) for x in d.get("passage_conditions", [])],
        passage=_passage_from_dict(d["passage"]),
    )


def _passage_to_dict(passage: Passage) -> dict[str, Any]:
    return {
        "kind": passage.kind.value,
        "state": passage.state,
        "traversable": passage.traversable,
        "sound_permeability": passage.sound_permeability,
    }


def _passage_from_dict(d: dict[str, Any]) -> Passage:
    return Passage(
        kind=PassageKindEnum(d["kind"]),
        state=str(d["state"]),
        traversable=bool(d["traversable"]),
        sound_permeability=float(d["sound_permeability"]),
    )


def _passage_condition_to_dict(p: PassageCondition) -> dict[str, Any]:
    return {
        "condition_type": _enum_name(p.condition_type),
        "item_spec_id": int(p.item_spec_id.value) if p.item_spec_id is not None else None,
        "flag_name": p.flag_name,
        "consume_item": p.consume_item,
        "failure_message": p.failure_message,
    }


def _passage_condition_from_dict(d: dict[str, Any]) -> PassageCondition:
    return PassageCondition(
        condition_type=_parse_enum(PassageConditionTypeEnum, d["condition_type"]),
        item_spec_id=ItemSpecId.create(int(d["item_spec_id"])) if d.get("item_spec_id") is not None else None,
        flag_name=d.get("flag_name"),
        consume_item=bool(d.get("consume_item", False)),
        failure_message=str(d.get("failure_message", "")),
    )


def _sub_location_to_dict(s: SubLocation) -> dict[str, Any]:
    out: dict[str, Any] = {
        "sub_location_id": int(s.sub_location_id.value),
        "name": s.name,
        "description": s.description,
        "accessible_object_ids": [int(x.value) for x in s.accessible_object_ids],
        "is_hidden": s.is_hidden,
    }
    if s.discovery_condition is not None:
        out["discovery_condition"] = _discovery_condition_to_dict(s.discovery_condition)
    return out


def _sub_location_from_dict(d: dict[str, Any]) -> SubLocation:
    dc = _discovery_condition_from_dict(d["discovery_condition"]) if d.get("discovery_condition") else None
    return SubLocation(
        sub_location_id=SubLocationId.create(int(d["sub_location_id"])),
        name=d["name"],
        description=d["description"],
        accessible_object_ids=tuple(SpotObjectId.create(int(x)) for x in d["accessible_object_ids"]),
        is_hidden=bool(d["is_hidden"]),
        discovery_condition=dc,
    )


def _discovery_condition_to_dict(dc: DiscoveryCondition) -> dict[str, Any]:
    return {
        "condition_type": _enum_name(dc.condition_type),
        "required_search_count": dc.required_search_count,
        "required_item_spec_id": int(dc.required_item_spec_id.value) if dc.required_item_spec_id else None,
        "flag_name": dc.flag_name,
    }


def _discovery_condition_from_dict(d: dict[str, Any]) -> DiscoveryCondition:
    return DiscoveryCondition(
        condition_type=_parse_enum(DiscoveryConditionTypeEnum, d["condition_type"]),
        required_search_count=int(d.get("required_search_count", 1)),
        required_item_spec_id=ItemSpecId.create(int(d["required_item_spec_id"])) if d.get("required_item_spec_id") else None,
        flag_name=d.get("flag_name"),
    )


def _spot_object_to_dict(o: SpotObject) -> dict[str, Any]:
    return {
        "object_id": int(o.object_id.value),
        "name": o.name,
        "description": o.description,
        "object_type": _enum_name(o.object_type),
        "state": o.state,
        "interactions": [_interaction_def_to_dict(i) for i in o.interactions],
        "is_visible": o.is_visible,
    }


def _spot_object_from_dict(d: dict[str, Any]) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(int(d["object_id"])),
        name=d["name"],
        description=d["description"],
        object_type=_parse_enum(SpotObjectTypeEnum, d["object_type"]),
        state=dict(d.get("state", {})),
        interactions=tuple(_interaction_def_from_dict(x) for x in d["interactions"]),
        is_visible=bool(d.get("is_visible", True)),
    )


def _interaction_def_to_dict(i: InteractionDef) -> dict[str, Any]:
    return {
        "action_name": i.action_name,
        "display_label": i.display_label,
        "preconditions": [_interaction_condition_to_dict(p) for p in i.preconditions],
        "effects": [_interaction_effect_to_dict(e) for e in i.effects],
    }


def _interaction_def_from_dict(d: dict[str, Any]) -> InteractionDef:
    return InteractionDef(
        action_name=d["action_name"],
        display_label=d["display_label"],
        preconditions=tuple(_interaction_condition_from_dict(x) for x in d["preconditions"]),
        effects=tuple(_interaction_effect_from_dict(x) for x in d["effects"]),
    )


def _interaction_condition_to_dict(p: InteractionCondition) -> dict[str, Any]:
    return {
        "condition_type": _enum_name(p.condition_type),
        "target_item_spec_id": int(p.target_item_spec_id.value) if p.target_item_spec_id else None,
        "target_object_id": int(p.target_object_id.value) if p.target_object_id else None,
        "required_state": p.required_state,
        "flag_name": p.flag_name,
        "failure_message": p.failure_message,
    }


def _interaction_condition_from_dict(d: dict[str, Any]) -> InteractionCondition:
    return InteractionCondition(
        condition_type=_parse_enum(InteractionConditionTypeEnum, d["condition_type"]),
        target_item_spec_id=ItemSpecId.create(int(d["target_item_spec_id"])) if d.get("target_item_spec_id") else None,
        target_object_id=SpotObjectId.create(int(d["target_object_id"])) if d.get("target_object_id") else None,
        required_state=d.get("required_state"),
        flag_name=d.get("flag_name"),
        failure_message=str(d.get("failure_message", "")),
    )


def _interaction_effect_to_dict(e: InteractionEffect) -> dict[str, Any]:
    return {"effect_type": _enum_name(e.effect_type), "parameters": dict(e.parameters)}


def _interaction_effect_from_dict(d: dict[str, Any]) -> InteractionEffect:
    return InteractionEffect(
        effect_type=_parse_enum(InteractionEffectTypeEnum, d["effect_type"]),
        parameters=dict(d.get("parameters", {})),
    )


def _ground_item_to_dict(g: GroundItem) -> dict[str, Any]:
    return {
        "item_instance_id": int(g.item_instance_id.value),
        "item_spec_id": int(g.item_spec_id.value),
    }


def _ground_item_from_dict(d: dict[str, Any]) -> GroundItem:
    return GroundItem(
        item_instance_id=ItemInstanceId.create(int(d["item_instance_id"])),
        item_spec_id=ItemSpecId.create(int(d["item_spec_id"])),
    )


def _discoverable_item_to_dict(di: DiscoverableItem) -> dict[str, Any]:
    return {
        "item_spec_id": int(di.item_spec_id.value),
        "discovery_condition": _discovery_condition_to_dict(di.discovery_condition),
        "is_discovered": di.is_discovered,
        "description": di.description,
    }


def _discoverable_item_from_dict(d: dict[str, Any]) -> DiscoverableItem:
    return DiscoverableItem(
        item_spec_id=ItemSpecId.create(int(d["item_spec_id"])),
        discovery_condition=_discovery_condition_from_dict(d["discovery_condition"]),
        is_discovered=bool(d.get("is_discovered", False)),
        description=str(d.get("description", "")),
    )


__all__ = [
    "AGGREGATE_SCHEMA_VERSION",
    "INTERIOR_SCHEMA_VERSION",
    "dumps_spot_graph_aggregate",
    "dumps_spot_interior",
    "loads_spot_graph_aggregate",
    "loads_spot_interior",
    "spot_graph_aggregate_from_json_dict",
    "spot_graph_aggregate_to_json_dict",
    "spot_interior_from_json_dict",
    "spot_interior_to_json_dict",
]
