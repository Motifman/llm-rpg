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
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.enum.trap_trigger_type import TrapTriggerTypeEnum
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
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
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
)
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.infrastructure.repository.spot_graph_persistence_exceptions import (
    SpotGraphConnectionRecordInvariantError,
    SpotGraphStateDecodeError,
    UnsupportedSpotGraphAggregateSchemaError,
    UnsupportedSpotInteriorSchemaError,
)

E = TypeVar("E", bound=Enum)


def _enum_name(value: Enum) -> str:
    return value.name


def _parse_enum(enum_cls: Type[E], name: str) -> E:
    return enum_cls[name]


AGGREGATE_SCHEMA_VERSION = 3
INTERIOR_SCHEMA_VERSION = 4


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
    if version not in (1, 2, AGGREGATE_SCHEMA_VERSION):
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
    if version not in (1, 2, 3, INTERIOR_SCHEMA_VERSION):
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
        "is_outdoor": node.is_outdoor,
        "traps": [_trap_def_to_dict(trap) for trap in node.traps],
    }
    if node.atmosphere is not None:
        d["atmosphere"] = _spot_atmosphere_to_dict(node.atmosphere)
    if node.position is not None:
        d["position"] = _spot_position_to_dict(node.position)
    if node.area_id is not None:
        d["area_id"] = node.area_id
    return d


def _spot_node_from_dict(d: dict[str, Any]) -> SpotNode:
    parent = SpotId.create(int(d["parent_id"])) if d.get("parent_id") is not None else None
    atmosphere = _spot_atmosphere_from_dict(d["atmosphere"]) if d.get("atmosphere") else None
    position = _spot_position_from_dict(d["position"]) if d.get("position") is not None else None
    traps_payload = d.get("traps", [])
    if not isinstance(traps_payload, list):
        raise SpotGraphStateDecodeError("spot node traps must be an array")
    try:
        return SpotNode(
            spot_id=SpotId.create(int(d["spot_id"])),
            name=d["name"],
            description=d["description"],
            category=_parse_enum(SpotCategoryEnum, d["category"]),
            parent_id=parent,
            interior=None,
            atmosphere=atmosphere,
            is_outdoor=_decode_optional_bool(
                d, "is_outdoor", default=False, owner="spot node"
            ),
            traps=tuple(_trap_def_from_dict(trap) for trap in traps_payload),
            position=position,
            area_id=d.get("area_id"),
        )
    except SpotGraphStateDecodeError:
        raise
    except Exception as exc:
        raise SpotGraphStateDecodeError(
            f"invalid spot node payload: {exc}"
        ) from exc


def _spot_position_to_dict(position: SpotPosition) -> dict[str, float]:
    return {"x": float(position.x), "y": float(position.y)}


def _spot_position_from_dict(d: dict[str, Any]) -> SpotPosition:
    return SpotPosition(x=float(d["x"]), y=float(d["y"]))


def _spot_atmosphere_to_dict(a: SpotAtmosphere) -> dict[str, Any]:
    return {
        "lighting": _enum_name(a.lighting),
        "sound_ambient": a.sound_ambient,
        "temperature": _enum_name(a.temperature),
        "smell": a.smell,
        # Phase 5: 環境音の強度 (default SILENT で後方互換)
        "sound_intensity": _enum_name(a.sound_intensity),
    }


def _spot_atmosphere_from_dict(d: dict[str, Any]) -> SpotAtmosphere:
    return SpotAtmosphere(
        lighting=_parse_enum(LightingEnum, d["lighting"]),
        sound_ambient=d.get("sound_ambient"),
        temperature=_parse_enum(TemperatureEnum, d.get("temperature", "NORMAL")),
        smell=d.get("smell"),
        # Phase 5: 旧スキーマ row には sound_intensity が無いので SILENT
        # を default として返す (= 「音なし」と同等で後方互換)。
        sound_intensity=_parse_enum(
            SoundIntensityEnum, d.get("sound_intensity", "SILENT"),
        ),
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
    payload = {
        "kind": passage.kind.value,
        "state": passage.state,
        "traversable": passage.traversable,
        "sound_permeability": passage.sound_permeability,
    }
    if passage.state_overrides:
        payload["overrides"] = {
            override.state: {
                key: value
                for key, value in (
                    ("traversable", override.traversable),
                    ("sound_permeability", override.sound_permeability),
                )
                if value is not None
            }
            for override in passage.state_overrides
        }
    return payload


def _passage_from_dict(d: dict[str, Any]) -> Passage:
    try:
        # SQLite payload はシナリオ入力と違い完全な実効状態を要求する。
        # Passage.from_dict のシナリオ向け既定値で欠落を補わない。
        for required_key in (
            "kind",
            "state",
            "traversable",
            "sound_permeability",
        ):
            d[required_key]
        return Passage.from_dict(d)
    except KeyError as exc:
        # legacy フィールド (is_passable / sound_permeability) しか持たない旧スキーマ
        # の DB を読み込んだ場合などに発生する。pre-release のため、再生成を促す
        # メッセージで早期に気づけるようにする。
        raise SpotGraphStateDecodeError(
            f"接続の passage フィールドが欠落しています (missing key: {exc}). "
            f"旧スキーマの DB の可能性があります。利用したシナリオ入口から "
            f"DB を再生成してください。"
        ) from exc


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
    out = {
        "object_id": int(o.object_id.value),
        "name": o.name,
        "description": o.description,
        "object_type": _enum_name(o.object_type),
        "state": o.state,
        "interactions": [_interaction_def_to_dict(i) for i in o.interactions],
        "is_visible": o.is_visible,
        "is_visible_in_dark": o.is_visible_in_dark,
        "trap": _trap_def_to_dict(o.trap) if o.trap is not None else None,
    }
    if o.unavailable_hint is not None:
        out["unavailable_hint"] = o.unavailable_hint
    if o.hidden_state_keys:
        out["hidden_state_keys"] = sorted(o.hidden_state_keys)
    if o.state_display:
        out["state_display"] = [_state_display_rule_to_dict(rule) for rule in o.state_display]
    return out


def _spot_object_from_dict(d: dict[str, Any]) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(int(d["object_id"])),
        name=d["name"],
        description=d["description"],
        object_type=_parse_enum(SpotObjectTypeEnum, d["object_type"]),
        state=dict(d.get("state", {})),
        interactions=tuple(_interaction_def_from_dict(x) for x in d["interactions"]),
        is_visible=bool(d.get("is_visible", True)),
        is_visible_in_dark=bool(d.get("is_visible_in_dark", False)),
        trap=_trap_def_from_dict(d["trap"]) if d.get("trap") is not None else None,
        unavailable_hint=d.get("unavailable_hint"),
        hidden_state_keys=frozenset(d.get("hidden_state_keys", ())),
        state_display=tuple(_state_display_rule_from_dict(x) for x in d.get("state_display", ())),
    )


def _state_display_rule_to_dict(rule: StateDisplayRule) -> dict[str, Any]:
    out = {"key": rule.key, "text": rule.text}
    if rule.within_ticks is not None:
        out["within_ticks"] = rule.within_ticks
    elif rule.at_least is not None:
        out["at_least"] = rule.at_least
    else:
        out["value"] = rule.value
    if rule.requires_light:
        out["requires_light"] = True
    if rule.unless_flag_set is not None:
        out["unless_flag_set"] = rule.unless_flag_set
    return out


def _state_display_rule_from_dict(d: dict[str, Any]) -> StateDisplayRule:
    return StateDisplayRule(
        key=d["key"],
        value=d.get("value"),
        text=d["text"],
        at_least=d.get("at_least"),
        within_ticks=d.get("within_ticks"),
        requires_light=d.get("requires_light", False),
        unless_flag_set=d.get("unless_flag_set"),
    )


def _interaction_def_to_dict(i: InteractionDef) -> dict[str, Any]:
    out: dict[str, Any] = {
        "action_name": i.action_name,
        "display_label": i.display_label,
        "preconditions": [_interaction_condition_to_dict(p) for p in i.preconditions],
        "effects": [_interaction_effect_to_dict(e) for e in i.effects],
    }
    if i.on_failure_observation is not None:
        out["on_failure_observation"] = i.on_failure_observation
    if i.witness_observation_message is not None:
        out["witness_observation_message"] = i.witness_observation_message
    if i.witness_observation_message_in_dark is not None:
        out["witness_observation_message_in_dark"] = (
            i.witness_observation_message_in_dark
        )
    if i.witness_policy is not WitnessPolicy.SAME_SPOT:
        out["witness_policy"] = i.witness_policy.value
    if i.notify_target:
        out["notify_target"] = True
    if i.target_observation_message is not None:
        out["target_observation_message"] = i.target_observation_message
    if i.cooldown_ticks:
        out["cooldown_ticks"] = i.cooldown_ticks
    if i.cooldown_group is not None:
        out["cooldown_group"] = i.cooldown_group
    if i.cooldown_scope is not InteractionCooldownScope.ACTOR:
        out["cooldown_scope"] = i.cooldown_scope.value
    out["allowed_actor_planes"] = [plane.value for plane in i.allowed_actor_planes]
    if i.hide_when_flag_preconditions_fail:
        out["hide_when_flag_preconditions_fail"] = True
    return out


def _interaction_def_from_dict(d: dict[str, Any]) -> InteractionDef:
    from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
        InteractionActorPlane,
    )

    return InteractionDef(
        action_name=d["action_name"],
        display_label=d["display_label"],
        preconditions=tuple(_interaction_condition_from_dict(x) for x in d["preconditions"]),
        effects=tuple(_interaction_effect_from_dict(x) for x in d["effects"]),
        on_failure_observation=d.get("on_failure_observation"),
        witness_observation_message=d.get("witness_observation_message"),
        witness_observation_message_in_dark=d.get(
            "witness_observation_message_in_dark"
        ),
        witness_policy=WitnessPolicy(d.get("witness_policy", WitnessPolicy.SAME_SPOT.value)),
        notify_target=_decode_optional_bool(
            d, "notify_target", default=False, owner="interaction"
        ),
        target_observation_message=_decode_optional_string(
            d, "target_observation_message", owner="interaction"
        ),
        cooldown_ticks=int(d.get("cooldown_ticks", 0)),
        cooldown_group=d.get("cooldown_group"),
        cooldown_scope=InteractionCooldownScope(
            d.get("cooldown_scope", InteractionCooldownScope.ACTOR.value)
        ),
        allowed_actor_planes=tuple(
            InteractionActorPlane(value)
            for value in d.get("allowed_actor_planes", ["LIVING"])
        ),
        hide_when_flag_preconditions_fail=_decode_optional_bool(
            d,
            "hide_when_flag_preconditions_fail",
            default=False,
            owner="interaction",
        ),
    )


_INTERACTION_CONDITION_FIELD_CODECS = {
    "condition_type": "condition_type",
    "target_item_spec_id": "optional_item_spec_id",
    "target_object_id": "optional_spot_object_id",
    "required_state": "optional_dict",
    "flag_name": "optional_str",
    "failure_message": "str",
    "required_player_count": "optional_int",
    "prepared_action_id": "optional_str",
    "puzzle_input_key": "optional_str",
    "required_item_spec_ids": "optional_item_spec_ids",
    "required_quantity": "int",
    "state_key": "optional_str",
    "need_type": "optional_str",
    "need_threshold": "optional_int",
    "gold_threshold": "optional_int",
    "hp_ratio": "optional_float",
    "required_time_of_day_phase": "optional_str",
    "required_weather_type": "optional_str",
    "item_spec_id_parameter_key": "optional_str",
    "required_lighting": "optional_str",
    "required_spot_id": "optional_spot_id",
}


def _interaction_condition_to_dict(p: InteractionCondition) -> dict[str, Any]:
    return {
        field_name: _encode_interaction_condition_value(
            field_name, codec_name, getattr(p, field_name)
        )
        for field_name, codec_name in _INTERACTION_CONDITION_FIELD_CODECS.items()
    }


def _interaction_condition_from_dict(d: dict[str, Any]) -> InteractionCondition:
    if "condition_type" not in d:
        raise SpotGraphStateDecodeError(
            "interaction condition payload requires condition_type"
        )
    defaults = InteractionCondition(
        condition_type=InteractionConditionTypeEnum.ALWAYS
    )
    try:
        values = {
            field_name: _decode_interaction_condition_value(
                field_name,
                codec_name,
                d.get(field_name, getattr(defaults, field_name)),
            )
            for field_name, codec_name in _INTERACTION_CONDITION_FIELD_CODECS.items()
        }
        return InteractionCondition(**values)
    except SpotGraphStateDecodeError:
        raise
    except Exception as exc:
        raise SpotGraphStateDecodeError(
            f"invalid interaction condition payload: {exc}"
        ) from exc


def _encode_interaction_condition_value(
    field_name: str, codec_name: str, value: Any,
) -> Any:
    if codec_name == "condition_type":
        return _enum_name(value)
    if codec_name in ("optional_item_spec_id", "optional_spot_object_id", "optional_spot_id"):
        return int(value.value) if value is not None else None
    if codec_name == "optional_item_spec_ids":
        return [int(item_spec_id.value) for item_spec_id in value] if value is not None else None
    return value


def _decode_interaction_condition_value(
    field_name: str, codec_name: str, value: Any,
) -> Any:
    def fail(expected: str) -> None:
        raise SpotGraphStateDecodeError(
            f"interaction condition {field_name} must be {expected}"
        )

    if codec_name == "condition_type":
        if not isinstance(value, str):
            fail("a str")
        return _parse_enum(InteractionConditionTypeEnum, value)
    if codec_name == "str":
        if not isinstance(value, str):
            fail("a str")
        return value
    if codec_name == "optional_str":
        if value is not None and not isinstance(value, str):
            fail("a str or None")
        return value
    if codec_name in ("int", "optional_int"):
        if value is None and codec_name == "optional_int":
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            fail("an int")
        return value
    if codec_name == "optional_float":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail("a number or None")
        return float(value)
    if codec_name == "optional_dict":
        if value is not None and not isinstance(value, dict):
            fail("an object or None")
        return value
    if codec_name == "optional_item_spec_ids":
        if value is None:
            return None
        if not isinstance(value, list):
            fail("an array or None")
        return tuple(
            ItemSpecId.create(_decode_json_int(field_name, item_value))
            for item_value in value
        )
    if value is None:
        return None
    int_value = _decode_json_int(field_name, value)
    if codec_name == "optional_item_spec_id":
        return ItemSpecId.create(int_value)
    if codec_name == "optional_spot_object_id":
        return SpotObjectId.create(int_value)
    if codec_name == "optional_spot_id":
        return SpotId.create(int_value)
    raise SpotGraphStateDecodeError(
        f"unknown interaction condition codec for {field_name}: {codec_name}"
    )


def _decode_json_int(field_name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpotGraphStateDecodeError(
            f"interaction condition {field_name} must contain integers"
        )
    return value


def _interaction_effect_to_dict(e: InteractionEffect) -> dict[str, Any]:
    return {
        "effect_type": _enum_name(e.effect_type),
        "parameters": dict(e.parameters),
        "visibility": e.visibility.value if e.visibility is not None else None,
        "target": e.target.value,
    }


def _interaction_effect_from_dict(d: dict[str, Any]) -> InteractionEffect:
    try:
        visibility_value = d.get("visibility")
        target_value = d.get("target", EffectTarget.ACTOR.value)
        if visibility_value is not None and not isinstance(visibility_value, str):
            raise SpotGraphStateDecodeError(
                "interaction effect visibility must be a str or None"
            )
        if not isinstance(target_value, str):
            raise SpotGraphStateDecodeError(
                "interaction effect target must be a str"
            )
        parameters = d.get("parameters", {})
        if not isinstance(parameters, dict):
            raise SpotGraphStateDecodeError(
                "interaction effect parameters must be an object"
            )
        return InteractionEffect(
            effect_type=_parse_enum(InteractionEffectTypeEnum, d["effect_type"]),
            parameters=dict(parameters),
            visibility=(
                EffectVisibility(visibility_value)
                if visibility_value is not None
                else None
            ),
            target=EffectTarget(target_value),
        )
    except SpotGraphStateDecodeError:
        raise
    except Exception as exc:
        raise SpotGraphStateDecodeError(
            f"invalid interaction effect payload: {exc}"
        ) from exc


def _trap_def_to_dict(trap: TrapDef) -> dict[str, Any]:
    return {
        "trap_id": trap.trap_id,
        "trigger_type": _enum_name(trap.trigger_type),
        "effects": [_interaction_effect_to_dict(effect) for effect in trap.effects],
        "is_hidden": trap.is_hidden,
        "is_repeating": trap.is_repeating,
        "disarm_conditions": [
            _interaction_condition_to_dict(condition)
            for condition in trap.disarm_conditions
        ],
        "detection_difficulty": trap.detection_difficulty,
    }


def _trap_def_from_dict(d: dict[str, Any]) -> TrapDef:
    if not isinstance(d, dict):
        raise SpotGraphStateDecodeError("trap payload must be an object")
    effects = d.get("effects")
    disarm_conditions = d.get("disarm_conditions", [])
    if not isinstance(effects, list):
        raise SpotGraphStateDecodeError("trap effects must be an array")
    if not isinstance(disarm_conditions, list):
        raise SpotGraphStateDecodeError(
            "trap disarm_conditions must be an array"
        )
    trap_id = d.get("trap_id")
    trigger_type = d.get("trigger_type")
    detection_difficulty = d.get("detection_difficulty", 0)
    if not isinstance(trap_id, str):
        raise SpotGraphStateDecodeError("trap trap_id must be a str")
    if not isinstance(trigger_type, str):
        raise SpotGraphStateDecodeError("trap trigger_type must be a str")
    if isinstance(detection_difficulty, bool) or not isinstance(
        detection_difficulty, int
    ):
        raise SpotGraphStateDecodeError(
            "trap detection_difficulty must be an int"
        )
    try:
        return TrapDef(
            trap_id=trap_id,
            trigger_type=_parse_enum(TrapTriggerTypeEnum, trigger_type),
            effects=tuple(_interaction_effect_from_dict(effect) for effect in effects),
            is_hidden=_decode_optional_bool(
                d, "is_hidden", default=True, owner="trap"
            ),
            is_repeating=_decode_optional_bool(
                d, "is_repeating", default=False, owner="trap"
            ),
            disarm_conditions=tuple(
                _interaction_condition_from_dict(condition)
                for condition in disarm_conditions
            ),
            detection_difficulty=detection_difficulty,
        )
    except SpotGraphStateDecodeError:
        raise
    except Exception as exc:
        raise SpotGraphStateDecodeError(
            f"invalid trap payload: {exc}"
        ) from exc


def _decode_optional_bool(
    payload: dict[str, Any], key: str, *, default: bool, owner: str,
) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise SpotGraphStateDecodeError(f"{owner} {key} must be a bool")
    return value


def _decode_optional_string(
    payload: dict[str, Any], key: str, *, owner: str,
) -> Optional[str]:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise SpotGraphStateDecodeError(f"{owner} {key} must be a str or None")
    return value


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
