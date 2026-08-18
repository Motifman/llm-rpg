"""spots / 地図 / 接続 / 遠景の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import ObjectDescriptionVariant
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.infrastructure.scenario.declaration_site import declaring
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.models import (
    AreaDef,
    DistantCueAppearEventDef,
    DistantCueDef,
    DistantCueSourceDef,
)
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    area_centroid,
    is_json_primitive,
    parse_bool,
    parse_object_hidden_state_keys,
    parse_object_state_display,
    parse_position_number,
    parse_prominence,
    recorded_tick_state_keys,
    spot_positions_by_area,
)
from ai_rpg_world.infrastructure.scenario.parse_interactions import parse_interaction_def
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def parse_spots_and_graph(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    remote_recorded_tick_keys: Mapping[int, frozenset[str]],
    player_attribute_specs: PlayerAttributeSpecs,
) -> Tuple[SpotGraphAggregate, Dict[SpotId, SpotInterior]]:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    interiors: Dict[SpotId, SpotInterior] = {}

    for spot_raw in raw.get("spots", []):
        sid_str = spot_raw["id"]
        spot_int = mapper.register("spot", sid_str)
        spot_id = SpotId.create(spot_int)

        atmosphere = parse_atmosphere(spot_raw.get("atmosphere"))
        parent_str = spot_raw.get("parent_id")
        parent_id = SpotId.create(mapper.get_int("spot", parent_str)) if parent_str else None
        category = SpotCategoryEnum[spot_raw.get("category", "OTHER")]
        position = parse_spot_position(sid_str, spot_raw.get("position"))
        area_id = parse_spot_area_id(sid_str, spot_raw.get("area_id"))

        node = SpotNode(
            spot_id=spot_id,
            name=spot_raw["name"],
            description=spot_raw["description"],
            category=category,
            parent_id=parent_id,
            interior=None,
            atmosphere=atmosphere,
            is_outdoor=parse_bool(
                spot_raw.get("is_outdoor", False),
                path=f"spot {sid_str}.is_outdoor",
            ),
            position=position,
            area_id=area_id,
        )
        graph.add_spot(node)

        interior_raw = spot_raw.get("interior")
        if interior_raw:
            with declaring(f"spot {sid_str!r} の"):
                interiors[spot_id] = parse_interior(
                    interior_raw,
                    mapper,
                    remote_recorded_tick_keys=remote_recorded_tick_keys,
                    player_attribute_specs=player_attribute_specs,
                )
        else:
            interiors[spot_id] = SpotInterior.empty()

    graph.clear_events()
    return graph, interiors

def parse_spot_position( spot_id: str, raw: Any) -> Optional[SpotPosition]:
    if raw is None:
        return None
    path = f"spots[{spot_id}].position"
    if not isinstance(raw, Mapping):
        raise ScenarioLoadError(f"{path} must be an object with numeric x/y")
    unknown_keys = set(raw) - {"x", "y"}
    if unknown_keys:
        raise ScenarioLoadError(
            f"{path} has unsupported keys: {sorted(unknown_keys)}"
        )
    x = parse_position_number(raw.get("x"), f"{path}.x")
    y = parse_position_number(raw.get("y"), f"{path}.y")
    return SpotPosition(x=x, y=y)

def parse_spot_area_id( spot_id: str, raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ScenarioLoadError(f"spots[{spot_id}].area_id must be a non-empty string")
    return raw.strip()

def parse_areas(
    areas_raw: Any,
    spots_raw: Any,
) -> Tuple[AreaDef, ...]:
    if areas_raw is None:
        return ()
    if not isinstance(areas_raw, Sequence) or isinstance(areas_raw, (str, bytes)):
        raise ScenarioLoadError("areas must be a list")

    area_spot_positions = spot_positions_by_area(spots_raw)
    out: List[AreaDef] = []
    seen: set[str] = set()
    for index, raw_area in enumerate(areas_raw):
        if not isinstance(raw_area, Mapping):
            raise ScenarioLoadError(f"areas[{index}] must be an object")
        area_id = raw_area.get("id")
        if not isinstance(area_id, str) or not area_id.strip():
            raise ScenarioLoadError(f"areas[{index}].id must be a non-empty string")
        area_id = area_id.strip()
        if area_id in seen:
            raise ScenarioLoadError(f"areas[{area_id}].id is duplicated")
        seen.add(area_id)

        name = raw_area.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ScenarioLoadError(f"areas[{area_id}].name must be a non-empty string")
        visible_name = raw_area.get("visible_name")
        if not isinstance(visible_name, str) or not visible_name.strip():
            raise ScenarioLoadError(
                f"areas[{area_id}].visible_name must be a non-empty string"
            )
        prominence = parse_prominence(
            raw_area.get("prominence"), f"areas[{area_id}].prominence"
        )

        declared_position = parse_area_position(area_id, raw_area.get("position"))
        if declared_position is not None:
            position = declared_position
            position_source = "declared"
        else:
            position = area_centroid(area_spot_positions.get(area_id, ()))
            position_source = "centroid" if position is not None else None

        distant_descriptions = raw_area.get("distant_descriptions", {})
        if distant_descriptions is None:
            distant_descriptions = {}
        if not isinstance(distant_descriptions, Mapping):
            raise ScenarioLoadError(
                f"areas[{area_id}].distant_descriptions must be an object"
            )
        out.append(
            AreaDef(
                area_id=area_id,
                name=name.strip(),
                visible_name=visible_name.strip(),
                prominence=prominence,
                position=position,
                position_source=position_source,
                description=str(raw_area.get("description", "") or ""),
                distant_descriptions={
                    str(k): str(v) for k, v in distant_descriptions.items()
                },
            )
        )
    return tuple(out)

def parse_area_position( area_id: str, raw: Any) -> Optional[SpotPosition]:
    if raw is None:
        return None
    path = f"areas[{area_id}].position"
    if not isinstance(raw, Mapping):
        raise ScenarioLoadError(f"{path} must be an object with numeric x/y")
    unknown_keys = set(raw) - {"x", "y"}
    if unknown_keys:
        raise ScenarioLoadError(
            f"{path} has unsupported keys: {sorted(unknown_keys)}"
        )
    x = parse_position_number(raw.get("x"), f"{path}.x")
    y = parse_position_number(raw.get("y"), f"{path}.y")
    return SpotPosition(x=x, y=y)

def parse_distant_cues(
    raw: Any,
    mapper: ScenarioIdMapper,
    area_ids: set[str],
) -> Tuple[DistantCueDef, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ScenarioLoadError("distant_cues must be a list")

    out: List[DistantCueDef] = []
    seen: set[str] = set()
    for index, raw_cue in enumerate(raw):
        if not isinstance(raw_cue, Mapping):
            raise ScenarioLoadError(f"distant_cues[{index}] must be an object")
        cue_id = raw_cue.get("id")
        if not isinstance(cue_id, str) or not cue_id.strip():
            raise ScenarioLoadError(
                f"distant_cues[{index}].id must be a non-empty string"
            )
        cue_id = cue_id.strip()
        if cue_id in seen:
            raise ScenarioLoadError(f"distant_cues[{cue_id}].id is duplicated")
        seen.add(cue_id)

        source = parse_distant_cue_source(cue_id, raw_cue.get("source"), mapper)
        origin_area_id = parse_distant_cue_origin_area_id(
            cue_id, raw_cue.get("origin"), area_ids
        )

        visible_name = raw_cue.get("visible_name")
        if not isinstance(visible_name, str) or not visible_name.strip():
            raise ScenarioLoadError(
                f"distant_cues[{cue_id}].visible_name must be a non-empty string"
            )
        prominence = parse_prominence(
            raw_cue.get("prominence"), f"distant_cues[{cue_id}].prominence"
        )
        ambient_descriptions = raw_cue.get("ambient_descriptions", {})
        if ambient_descriptions is None:
            ambient_descriptions = {}
        if not isinstance(ambient_descriptions, Mapping):
            raise ScenarioLoadError(
                f"distant_cues[{cue_id}].ambient_descriptions must be an object"
            )
        appear_event = parse_distant_cue_appear_event(
            cue_id, raw_cue.get("appear_event")
        )

        out.append(
            DistantCueDef(
                cue_id=cue_id,
                source=source,
                origin_area_id=origin_area_id,
                visible_name=visible_name.strip(),
                prominence=prominence,
                ambient_descriptions={
                    str(k): str(v) for k, v in ambient_descriptions.items()
                },
                appear_event=appear_event,
            )
        )
    return tuple(out)

def parse_distant_cue_appear_event(
    cue_id: str,
    raw: Any,
) -> Optional[DistantCueAppearEventDef]:
    path = f"distant_cues[{cue_id}].appear_event"
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ScenarioLoadError(f"{path} must be an object")
    message = raw.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ScenarioLoadError(f"{path}.message must be a non-empty string")
    schedules_turn = raw.get("schedules_turn")
    if not isinstance(schedules_turn, bool):
        raise ScenarioLoadError(f"{path}.schedules_turn must be bool")
    return DistantCueAppearEventDef(
        message=message.strip(),
        schedules_turn=schedules_turn,
    )

def parse_distant_cue_source(
    cue_id: str,
    raw: Any,
    mapper: ScenarioIdMapper,
) -> DistantCueSourceDef:
    path = f"distant_cues[{cue_id}].source"
    if not isinstance(raw, Mapping):
        raise ScenarioLoadError(f"{path} must be an object")
    kind = raw.get("kind")
    if kind != "object_state":
        raise ScenarioLoadError(f"{path}.kind must be object_state")
    object_id_raw = raw.get("object_id")
    if not isinstance(object_id_raw, str) or not object_id_raw.strip():
        raise ScenarioLoadError(f"{path}.object_id must be a non-empty string")
    object_sid = object_id_raw.strip()
    try:
        object_id = SpotObjectId.create(mapper.get_int("object", object_sid))
    except ScenarioIdMappingError as exc:
        raise ScenarioLoadError(
            f"{path}.object_id references unknown object: {object_sid}"
        ) from exc
    state_key = raw.get("state_key")
    if not isinstance(state_key, str) or not state_key.strip():
        raise ScenarioLoadError(f"{path}.state_key must be a non-empty string")
    if "equals" not in raw:
        raise ScenarioLoadError(f"{path}.equals is required")
    equals = raw["equals"]
    if not is_json_primitive(equals):
        raise ScenarioLoadError(f"{path}.equals must be a JSON primitive")
    return DistantCueSourceDef(
        kind="object_state",
        object_id=object_id,
        state_key=state_key.strip(),
        equals=equals,
    )

def parse_distant_cue_origin_area_id(
    cue_id: str,
    raw: Any,
    area_ids: set[str],
) -> str:
    path = f"distant_cues[{cue_id}].origin"
    if not isinstance(raw, Mapping):
        raise ScenarioLoadError(f"{path} must be an object")
    area_id = raw.get("area_id")
    if not isinstance(area_id, str) or not area_id.strip():
        raise ScenarioLoadError(f"{path}.area_id must be a non-empty string")
    area_id = area_id.strip()
    if area_id not in area_ids:
        raise ScenarioLoadError(f"{path}.area_id references unknown area: {area_id}")
    return area_id

def parse_atmosphere( raw: Optional[Dict[str, Any]]) -> Optional[SpotAtmosphere]:
    if not raw:
        return None
    return SpotAtmosphere(
        lighting=LightingEnum[raw.get("lighting", "BRIGHT")],
        sound_ambient=raw.get("sound_ambient"),
        temperature=TemperatureEnum[raw.get("temperature", "NORMAL")],
        smell=raw.get("smell"),
    )

def parse_interior(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    remote_recorded_tick_keys: Mapping[int, frozenset[str]],
    player_attribute_specs: PlayerAttributeSpecs,
) -> SpotInterior:
    raw_objects = raw.get("objects", [])
    local_object_ids = {
        obj.get("id")
        for obj in raw_objects
        if isinstance(obj, dict) and isinstance(obj.get("id"), str)
    }
    sub_locs = tuple(
        parse_sub_location(
            s,
            mapper,
            local_object_ids=local_object_ids,
        )
        for s in raw.get("sub_locations", [])
    )
    objects = tuple(
        parse_spot_object(
            o,
            mapper,
            remote_recorded_tick_keys=remote_recorded_tick_keys,
            player_attribute_specs=player_attribute_specs,
        )
        for o in raw_objects
    )
    ground_items = ()  # ground_items は runtime で発生するため、シナリオ定義では空
    discoverables = tuple(
        parse_discoverable_item(d, mapper)
        for d in raw.get("discoverable_items", [])
    )
    return SpotInterior(
        sub_locations=sub_locs,
        objects=objects,
        ground_items=ground_items,
        discoverable_items=discoverables,
    )

def parse_sub_location(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    local_object_ids: set[str],
) -> SubLocation:
    sid = mapper.register("sub_location", raw["id"])
    raw_object_ids = raw.get("accessible_object_ids", [])
    if not isinstance(raw_object_ids, list):
        raise ScenarioLoadError(
            f"sub_location {raw.get('id')}.accessible_object_ids must be a list"
        )
    for object_id in raw_object_ids:
        if (
            not isinstance(object_id, str)
            or object_id not in local_object_ids
            or not mapper.contains("object", object_id)
        ):
            raise ScenarioLoadError(
                f"sub_location {raw.get('id')}.accessible_object_ids references "
                f"an object outside the same interior or an unknown object: "
                f"{object_id!r}"
            )
    obj_ids = tuple(
        SpotObjectId.create(mapper.get_int("object", oid))
        for oid in raw_object_ids
    )
    dc = parse_discovery_condition(raw.get("discovery_condition"), mapper) if raw.get("discovery_condition") else None
    return SubLocation(
        sub_location_id=SubLocationId.create(sid),
        name=raw["name"],
        description=raw["description"],
        accessible_object_ids=obj_ids,
        is_hidden=parse_bool(
            raw.get("is_hidden", False),
            path=f"sub_location {raw.get('id')}.is_hidden",
        ),
        discovery_condition=dc,
    )

def parse_spot_object(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    remote_recorded_tick_keys: Mapping[int, frozenset[str]],
    player_attribute_specs: PlayerAttributeSpecs,
) -> SpotObject:
    oid = mapper.register("object", raw["id"])
    with declaring(f"物体 {raw['id']!r} の"):
        interactions = tuple(
            parse_interaction_def(
                i, mapper, player_attribute_specs=player_attribute_specs
            )
            for i in raw.get("interactions", [])
        )
    variants = tuple(
        ObjectDescriptionVariant(
            description=str(v.get("description", "")),
            required_state=v.get("required_state"),
            required_flag=v.get("required_flag"),
        )
        for v in raw.get("description_variants", [])
    )
    unavailable_hint = raw.get("unavailable_hint")
    if unavailable_hint is not None:
        if not isinstance(unavailable_hint, str) or not unavailable_hint.strip():
            raise ScenarioLoadError(
                f"object {raw.get('id')}.unavailable_hint must be a non-empty string"
            )
    merged_recorded_tick_state_keys = (
        recorded_tick_state_keys(interactions, oid)
        | remote_recorded_tick_keys.get(oid, frozenset())
    )
    declared_hidden_state_keys = parse_object_hidden_state_keys(raw)
    state_display = parse_object_state_display(
        raw,
        recorded_tick_state_keys=merged_recorded_tick_state_keys,
    )
    # 作家が明示した key に、手番を記録する効果が書く key を足す。
    # 名前を当てにいくのではなく、宣言から導出する (#949 写しは腐る)。
    hidden_state_keys = declared_hidden_state_keys | merged_recorded_tick_state_keys
    return SpotObject(
        object_id=SpotObjectId.create(oid),
        name=raw["name"],
        description=raw["description"],
        object_type=SpotObjectTypeEnum[raw.get("object_type", "OTHER")],
        state=dict(raw.get("state", {})),
        interactions=interactions,
        description_variants=variants,
        is_visible=parse_bool(
            raw.get("is_visible", True),
            path=f"object {raw.get('id')}.is_visible",
        ),
        is_visible_in_dark=parse_bool(
            raw.get("is_visible_in_dark", False),
            path=f"object {raw.get('id')}.is_visible_in_dark",
        ),
        unavailable_hint=unavailable_hint,
        hidden_state_keys=hidden_state_keys,
        state_display=state_display,
    )

def parse_discoverable_item( raw: Dict[str, Any], mapper: ScenarioIdMapper) -> DiscoverableItem:
    item_sid = raw["item_spec"]
    dc = parse_discovery_condition(raw.get("discovery_condition", {}), mapper)
    return DiscoverableItem(
        item_spec_id=ItemSpecId.create(mapper.get_int("item_spec", item_sid)),
        discovery_condition=dc,
        is_discovered=False,
        description=raw.get("description", ""),
    )

def parse_discovery_condition( raw: Optional[Dict[str, Any]], mapper: ScenarioIdMapper) -> DiscoveryCondition:
    if not raw:
        return DiscoveryCondition(condition_type=DiscoveryConditionTypeEnum.ALWAYS)
    item_sid = raw.get("required_item")
    item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
    return DiscoveryCondition(
        condition_type=DiscoveryConditionTypeEnum[raw.get("condition_type", "ALWAYS")],
        required_search_count=int(raw.get("required_search_count", 1)),
        required_item_spec_id=item_spec_id,
        flag_name=raw.get("flag_name"),
    )

def parse_passage_condition( raw: Dict[str, Any], mapper: ScenarioIdMapper) -> PassageCondition:
    item_sid = raw.get("required_item")
    item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
    return PassageCondition(
        condition_type=PassageConditionTypeEnum[raw["condition_type"]],
        item_spec_id=item_spec_id,
        flag_name=raw.get("flag_name"),
        consume_item=parse_bool(
            raw.get("consume_item", False),
            path="passage_condition.consume_item",
        ),
        failure_message=raw.get("failure_message", ""),
    )

def parse_connections( conns_raw: List[Dict[str, Any]], graph: SpotGraphAggregate, mapper: ScenarioIdMapper,
) -> None:
    for c in conns_raw:
        cid = mapper.register("connection", c["id"])
        from_sid = mapper.get_int("spot", c["from"])
        to_sid = mapper.get_int("spot", c["to"])
        conditions = [parse_passage_condition(p, mapper) for p in c.get("passage_conditions", [])]
        is_bidir = parse_bool(
            c.get("is_bidirectional", True),
            path=f"connection {c.get('id')}.is_bidirectional",
        )
        # passage が無いシナリオは「開口部 (OPEN)」扱い。`initially_passable` /
        # 接続レベルの `sound_permeability` は廃止された旧スキーマのキーで、
        # 万一残っていれば作家への明示エラーにする。
        for legacy_key in ("initially_passable", "sound_permeability"):
            if legacy_key in c:
                raise ScenarioLoadError(
                    f"Connection '{c['id']}' uses obsolete key '{legacy_key}'. "
                    f"Use `passage` block instead."
                )
        passage = Passage.from_dict(c.get("passage"))

        conn = SpotConnection(
            connection_id=ConnectionId.create(cid),
            from_spot_id=SpotId.create(from_sid),
            to_spot_id=SpotId.create(to_sid),
            name=c["name"],
            description=c.get("description", ""),
            travel_ticks=int(c.get("travel_ticks", 1)),
            is_bidirectional=is_bidir,
            passage_conditions=conditions,
            passage=passage,
        )

        reverse_id: Optional[ConnectionId] = None
        if is_bidir:
            rev_str = c["id"] + "__reverse"
            rev_int = mapper.register("connection", rev_str)
            reverse_id = ConnectionId.create(rev_int)

        graph.add_connection(conn, reverse_connection_id=reverse_id)

    graph.clear_events()

