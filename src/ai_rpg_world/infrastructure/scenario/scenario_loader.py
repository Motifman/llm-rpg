"""シナリオ定義 JSON → ドメインオブジェクト変換。

scenario_format_version "1.0" に対応。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
)
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper


SUPPORTED_FORMAT_VERSIONS = ("1.0",)


class ScenarioLoadError(Exception):
    """シナリオ読み込み中のエラー。"""


@dataclass(frozen=True)
class ScenarioMetadata:
    id: str
    title: str
    description: str
    theme: str
    difficulty: str
    estimated_ticks: int
    author: str
    tags: Tuple[str, ...]
    #: LLM 初期文脈用。`description` のネタバレを避け、未プレイ者向けの公開レイヤーだけを書く（任意）。
    llm_public_intro: str = ""


@dataclass(frozen=True)
class ItemSpecDefinition:
    """シナリオ JSON で定義されたアイテム仕様。"""
    string_id: str
    spec_id: ItemSpecId
    name: str
    description: str
    category: str
    is_light_source: bool = False


@dataclass(frozen=True)
class PlayerSpawnConfig:
    """プレイヤー初期配置。"""
    string_id: str
    player_id: int
    name: str
    spawn_spot_id: SpotId
    initial_item_spec_ids: Tuple[ItemSpecId, ...]


@dataclass(frozen=True)
class ScenarioWeatherConfig:
    """Spot Graph シナリオ用の軽量天候設定。"""

    enabled: bool
    initial_state: WeatherState
    update_interval_ticks: int
    announce_changes: bool


@dataclass(frozen=True)
class ScenarioLoadResult:
    graph: SpotGraphAggregate
    interiors: Dict[SpotId, SpotInterior]
    win_conditions: Tuple[GameEndCondition, ...]
    lose_conditions: Tuple[GameEndCondition, ...]
    player_spawns: Tuple[PlayerSpawnConfig, ...]
    item_spec_definitions: Tuple[ItemSpecDefinition, ...]
    id_mapper: ScenarioIdMapper
    metadata: ScenarioMetadata
    initial_flags: Tuple[str, ...]
    scenario_events: Tuple[ScenarioEventDef, ...] = ()
    weather_config: Optional[ScenarioWeatherConfig] = None
    reactive_passage_bindings: Tuple[ReactivePassageBinding, ...] = ()
    reactive_object_state_bindings: Tuple[ReactiveObjectStateBinding, ...] = ()
    synchronized_action_groups: Tuple[SynchronizedActionGroup, ...] = ()


class ScenarioLoader:
    """シナリオ定義 JSON を読み込んでドメインオブジェクト群に変換する。"""

    def load_from_file(self, path: Path) -> ScenarioLoadResult:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return self.load_from_dict(raw)

    def load_from_dict(self, raw: Dict[str, Any]) -> ScenarioLoadResult:
        version = raw.get("scenario_format_version")
        if version not in SUPPORTED_FORMAT_VERSIONS:
            raise ScenarioLoadError(
                f"Unsupported scenario_format_version: {version!r}. "
                f"Supported: {SUPPORTED_FORMAT_VERSIONS}"
            )

        mapper = ScenarioIdMapper()

        metadata = self._parse_metadata(raw["metadata"])
        item_defs = self._parse_item_specs(raw.get("item_specs", []), mapper)
        self._pre_register_ids(raw, mapper)
        graph, interiors = self._parse_spots_and_graph(raw, mapper)
        self._parse_connections(raw.get("connections", []), graph, mapper)
        players = self._parse_players(raw.get("players", []), mapper)
        win_conds = self._parse_end_conditions(raw.get("game_end_conditions", {}).get("win", []), mapper)
        lose_conds = self._parse_end_conditions(raw.get("game_end_conditions", {}).get("lose", []), mapper)
        initial_flags = tuple(raw.get("initial_flags", []))
        scenario_events = self._parse_scenario_events(raw.get("scenario_events", []), mapper)
        weather_config = self._parse_weather_config(raw.get("environment", {}))
        reactive_bindings = self._parse_reactive_passage_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        reactive_object_bindings = self._parse_reactive_object_state_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        sync_groups = self._parse_synchronized_action_groups(
            raw.get("synchronized_action_groups", []), mapper,
        )

        return ScenarioLoadResult(
            graph=graph,
            interiors=interiors,
            win_conditions=tuple(win_conds),
            lose_conditions=tuple(lose_conds),
            player_spawns=tuple(players),
            item_spec_definitions=tuple(item_defs),
            id_mapper=mapper,
            metadata=metadata,
            initial_flags=initial_flags,
            scenario_events=scenario_events,
            weather_config=weather_config,
            reactive_passage_bindings=reactive_bindings,
            reactive_object_state_bindings=reactive_object_bindings,
            synchronized_action_groups=sync_groups,
        )

    def _parse_metadata(self, raw: Dict[str, Any]) -> ScenarioMetadata:
        return ScenarioMetadata(
            id=raw["id"],
            title=raw["title"],
            description=raw.get("description", ""),
            theme=raw.get("theme", ""),
            difficulty=raw.get("difficulty", "medium"),
            estimated_ticks=int(raw.get("estimated_ticks", 100)),
            author=raw.get("author", ""),
            tags=tuple(raw.get("tags", [])),
            llm_public_intro=str(raw.get("llm_public_intro", "") or "").strip(),
        )

    def _pre_register_ids(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> None:
        """スポット・接続・オブジェクトの全 ID を先行登録する。

        interaction effect が他スポットの接続やオブジェクトを参照する場合に備え、
        実体の解析よりも先に全名前空間の ID を確定させる。
        """
        for spot in raw.get("spots", []):
            mapper.register("spot", spot["id"])
            interior = spot.get("interior", {})
            for obj in interior.get("objects", []):
                mapper.register("object", obj["id"])
            for sub in interior.get("sub_locations", []):
                mapper.register("sub_location", sub["id"])
        for conn in raw.get("connections", []):
            mapper.register("connection", conn["id"])
            if conn.get("is_bidirectional", True):
                mapper.register("connection", conn["id"] + "__reverse")
        for player in raw.get("players", []):
            mapper.register("player", player["id"])

    def _parse_item_specs(
        self, items_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> List[ItemSpecDefinition]:
        defs: List[ItemSpecDefinition] = []
        for item in items_raw:
            sid = item["id"]
            numeric = mapper.register("item_spec", sid)
            defs.append(ItemSpecDefinition(
                string_id=sid,
                spec_id=ItemSpecId.create(numeric),
                name=item["name"],
                description=item.get("description", ""),
                category=item.get("category", "GENERAL"),
                is_light_source=item.get("is_light_source", False),
            ))
        return defs

    def _parse_spots_and_graph(
        self, raw: Dict[str, Any], mapper: ScenarioIdMapper,
    ) -> Tuple[SpotGraphAggregate, Dict[SpotId, SpotInterior]]:
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        interiors: Dict[SpotId, SpotInterior] = {}

        for spot_raw in raw.get("spots", []):
            sid_str = spot_raw["id"]
            spot_int = mapper.register("spot", sid_str)
            spot_id = SpotId.create(spot_int)

            atmosphere = self._parse_atmosphere(spot_raw.get("atmosphere"))
            parent_str = spot_raw.get("parent_id")
            parent_id = SpotId.create(mapper.get_int("spot", parent_str)) if parent_str else None
            category = SpotCategoryEnum[spot_raw.get("category", "OTHER")]

            node = SpotNode(
                spot_id=spot_id,
                name=spot_raw["name"],
                description=spot_raw["description"],
                category=category,
                parent_id=parent_id,
                interior=None,
                atmosphere=atmosphere,
                is_outdoor=bool(spot_raw.get("is_outdoor", False)),
            )
            graph.add_spot(node)

            interior_raw = spot_raw.get("interior")
            if interior_raw:
                interiors[spot_id] = self._parse_interior(interior_raw, mapper)
            else:
                interiors[spot_id] = SpotInterior.empty()

        graph.clear_events()
        return graph, interiors

    def _parse_atmosphere(self, raw: Optional[Dict[str, Any]]) -> Optional[SpotAtmosphere]:
        if not raw:
            return None
        return SpotAtmosphere(
            lighting=LightingEnum[raw.get("lighting", "BRIGHT")],
            sound_ambient=raw.get("sound_ambient"),
            temperature=TemperatureEnum[raw.get("temperature", "NORMAL")],
            smell=raw.get("smell"),
        )

    def _parse_interior(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> SpotInterior:
        sub_locs = tuple(
            self._parse_sub_location(s, mapper)
            for s in raw.get("sub_locations", [])
        )
        objects = tuple(
            self._parse_spot_object(o, mapper)
            for o in raw.get("objects", [])
        )
        ground_items = ()  # ground_items は runtime で発生するため、シナリオ定義では空
        discoverables = tuple(
            self._parse_discoverable_item(d, mapper)
            for d in raw.get("discoverable_items", [])
        )
        return SpotInterior(
            sub_locations=sub_locs,
            objects=objects,
            ground_items=ground_items,
            discoverable_items=discoverables,
        )

    def _parse_sub_location(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> SubLocation:
        sid = mapper.register("sub_location", raw["id"])
        obj_ids = tuple(
            SpotObjectId.create(mapper.get_int("object", oid))
            for oid in raw.get("accessible_object_ids", [])
            if mapper.contains("object", oid)
        )
        dc = self._parse_discovery_condition(raw.get("discovery_condition"), mapper) if raw.get("discovery_condition") else None
        return SubLocation(
            sub_location_id=SubLocationId.create(sid),
            name=raw["name"],
            description=raw["description"],
            accessible_object_ids=obj_ids,
            is_hidden=bool(raw.get("is_hidden", False)),
            discovery_condition=dc,
        )

    def _parse_spot_object(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> SpotObject:
        oid = mapper.register("object", raw["id"])
        interactions = tuple(
            self._parse_interaction_def(i, mapper) for i in raw.get("interactions", [])
        )
        variants = tuple(
            ObjectDescriptionVariant(
                description=str(v.get("description", "")),
                required_state=v.get("required_state"),
                required_flag=v.get("required_flag"),
            )
            for v in raw.get("description_variants", [])
        )
        return SpotObject(
            object_id=SpotObjectId.create(oid),
            name=raw["name"],
            description=raw["description"],
            object_type=SpotObjectTypeEnum[raw.get("object_type", "OTHER")],
            state=dict(raw.get("state", {})),
            interactions=interactions,
            description_variants=variants,
            is_visible=bool(raw.get("is_visible", True)),
        )

    def _parse_interaction_def(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionDef:
        preconds = tuple(
            self._parse_interaction_condition(c, mapper)
            for c in raw.get("preconditions", [])
        )
        effects = tuple(
            self._parse_interaction_effect(e, mapper) for e in raw.get("effects", [])
        )
        on_failure_observation = raw.get("on_failure_observation")
        return InteractionDef(
            action_name=raw["action_name"],
            display_label=raw["display_label"],
            preconditions=preconds,
            effects=effects,
            on_failure_observation=on_failure_observation,
        )

    def _parse_interaction_condition(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionCondition:
        item_sid = raw.get("required_item")
        item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
        obj_sid = raw.get("target_object")
        obj_id = SpotObjectId.create(mapper.get_int("object", obj_sid)) if obj_sid else None
        # 脱出ゲーム拡張フィールド
        required_items_raw = raw.get("required_items")
        required_item_spec_ids = None
        if required_items_raw:
            required_item_spec_ids = tuple(
                ItemSpecId.create(mapper.get_int("item_spec", s)) for s in required_items_raw
            )
        return InteractionCondition(
            condition_type=InteractionConditionTypeEnum[raw["condition_type"]],
            target_item_spec_id=item_spec_id,
            target_object_id=obj_id,
            required_state=raw.get("required_state"),
            flag_name=raw.get("flag_name"),
            failure_message=raw.get("failure_message", ""),
            required_player_count=raw.get("required_player_count"),
            prepared_action_id=raw.get("prepared_action_id"),
            puzzle_input_key=raw.get("puzzle_input_key"),
            required_item_spec_ids=required_item_spec_ids,
            required_quantity=self._parse_required_quantity(raw),
            need_type=self._parse_need_type(raw),
            need_threshold=raw.get("need_threshold"),
            hp_ratio=self._parse_hp_ratio(raw),
        )

    @staticmethod
    def _parse_need_type(raw: Dict[str, Any]) -> Optional[str]:
        """`need_type` が指定されていれば NeedType に存在する名前か load 時に検証する。

        ランタイムまで silent に間違いを引きずると「interaction が永久に
        発火しない」silent failure になるので boundary で弾く。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import NeedType

        value = raw.get("need_type")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ScenarioLoadError(
                f"need_type must be a string (got {type(value).__name__})"
            )
        try:
            NeedType(value)
        except ValueError as exc:
            valid = sorted(t.value for t in NeedType)
            raise ScenarioLoadError(
                f"need_type {value!r} is not a known NeedType. Valid values: {valid}"
            ) from exc
        return value

    @staticmethod
    def _parse_hp_ratio(raw: Dict[str, Any]) -> Optional[float]:
        """`hp_ratio` を 0.0..1.0 の範囲で検証する。範囲外は load 時に拒否。"""
        value = raw.get("hp_ratio")
        if value is None:
            return None
        try:
            f = float(value)
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"hp_ratio must be a number (got {value!r})"
            ) from exc
        if not (0.0 <= f <= 1.0):
            raise ScenarioLoadError(
                f"hp_ratio must be in [0.0, 1.0] (got {f})"
            )
        return f

    @staticmethod
    def _parse_required_quantity(raw: Dict[str, Any]) -> int:
        """`required_quantity` を読みつつ `<= 0` は明確に拒否する。

        domain 側で max(1, ...) する設計だが、scenario 作家が `0` を
        書いた場合に「条件無し」と勘違いするのを防ぐため、loader 側で
        早期に弾く。
        """
        if "required_quantity" not in raw:
            return 1
        try:
            value = int(raw["required_quantity"])
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"required_quantity must be a positive integer (got {raw['required_quantity']!r})"
            ) from exc
        if value <= 0:
            raise ScenarioLoadError(
                f"required_quantity must be >= 1 (got {value})"
            )
        return value

    def _parse_interaction_effect(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionEffect:
        params = dict(raw.get("parameters", {}))
        effect_type_str = raw.get("effect_type", "")
        # CHANGE_OBJECT_STATE は state_updates を正式名とする。
        # 過去シナリオ互換で new_state が来た場合は正規化して受け入れる。
        # 他の effect (CHANGE_PASSAGE_STATE 等) では new_state は別の意味で
        # 使われるため、CHANGE_OBJECT_STATE 限定で正規化する。
        if (
            effect_type_str == "CHANGE_OBJECT_STATE"
            and "state_updates" not in params
            and "new_state" in params
        ):
            params["state_updates"] = params.pop("new_state")
        if "item_spec" in params:
            params["item_spec_id"] = mapper.get_int("item_spec", params.pop("item_spec"))
        if "target_object" in params:
            params["object_id"] = mapper.get_int("object", params.pop("target_object"))
        if "target_sub_location" in params:
            params["sub_location_id"] = mapper.get_int("sub_location", params.pop("target_sub_location"))
        if "target_connection" in params:
            params["connection_id"] = mapper.get_int("connection", params.pop("target_connection"))
        if "target_spot" in params:
            params["spot_id"] = mapper.get_int("spot", params.pop("target_spot"))
        return InteractionEffect(
            effect_type=InteractionEffectTypeEnum[raw["effect_type"]],
            parameters=params,
        )

    def _parse_scenario_events(
        self,
        events_raw: Sequence[Dict[str, Any]],
        mapper: ScenarioIdMapper,
    ) -> Tuple[ScenarioEventDef, ...]:
        parsed: list[ScenarioEventDef] = []
        for raw in events_raw:
            observation = raw.get("observation", {})
            if not isinstance(observation, dict):
                observation = {}
            event_id = raw.get("id", "<unnamed>")
            conditions = tuple(
                self._parse_scenario_event_condition(
                    c, mapper, path=f"scenario_event[{event_id}].conditions[{i}]",
                )
                for i, c in enumerate(raw.get("conditions", []))
            )
            effects = tuple(
                self._parse_interaction_effect(e, mapper)
                for e in raw.get("effects", [])
            )
            parsed.append(
                ScenarioEventDef(
                    event_id=str(raw["id"]),
                    trigger=str(raw.get("trigger", "ON_TICK")),
                    once=bool(raw.get("once", True)),
                    conditions=conditions,
                    effects=effects,
                    observation_category=str(observation.get("category", "environment")),
                    recipients=str(observation.get("recipients", "all_players")),
                    target_spot_id=self._optional_spot_id(observation.get("target_spot"), mapper),
                    schedules_turn=bool(observation.get("schedules_turn", True)),
                    breaks_movement=bool(observation.get("breaks_movement", False)),
                    next_event_id=raw.get("next_event_id"),
                    delay_ticks=int(raw.get("delay_ticks", 0)),
                )
            )
        return tuple(parsed)

    def _optional_spot_id(self, value: Any, mapper: ScenarioIdMapper) -> Optional[int]:
        if not value:
            return None
        return mapper.get_int("spot", str(value))

    # 合成条件の糖衣記法: ネストの深い `condition_type: AND/OR/NOT + children`
    # を `all_of` / `any_of` / `not_` のフラットなキーで書けるようにする。
    # 内部 AST (ScenarioEventCondition) は変更しない — load 時に元の形へ
    # 正規化して通常経路に流す。
    _COMPOSITE_SUGAR: Dict[str, str] = {
        "all_of": "AND",
        "any_of": "OR",
        "not_": "NOT",
    }

    def _parse_scenario_event_condition(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        path: str = "condition",
    ) -> ScenarioEventCondition:
        # ---- 糖衣記法を従来形に正規化 ----
        # `all_of: [...]` / `any_of: [...]` / `not_: <cond>` の
        # いずれかが存在すれば `condition_type` + `children` 形に変換する。
        # `condition_type` と糖衣記法が同時にあるのは作家ミスとして拒否。
        sugar_keys = [k for k in self._COMPOSITE_SUGAR if k in raw]
        if sugar_keys:
            if len(sugar_keys) > 1:
                raise ScenarioLoadError(
                    f"{path}: multiple composite shortcuts found "
                    f"({sorted(sugar_keys)}); use only one of all_of/any_of/not_"
                )
            if "condition_type" in raw:
                raise ScenarioLoadError(
                    f"{path}: cannot mix 'condition_type' with composite "
                    f"shortcut '{sugar_keys[0]}'"
                )
            shortcut = sugar_keys[0]
            target_type = self._COMPOSITE_SUGAR[shortcut]
            payload = raw[shortcut]
            if shortcut == "not_":
                # not_ は単一条件を取る。list で書いても 1 要素まで許容するか
                # 迷うところだが、AST が 1 child 想定なので明確に dict 限定。
                if not isinstance(payload, dict):
                    raise ScenarioLoadError(
                        f"{path}: not_ must be a single condition object "
                        f"(got {type(payload).__name__})"
                    )
                children_list = [payload]
            else:
                if not isinstance(payload, list):
                    raise ScenarioLoadError(
                        f"{path}: {shortcut} must be a list "
                        f"(got {type(payload).__name__})"
                    )
                # list 内の各要素も dict であることを保証する。null や文字列が
                # 紛れ込むと再帰呼び出し先で raw KeyError になりエラーが
                # 不親切になるため、ここで早期に shortcut の path 付きで弾く。
                for i, item in enumerate(payload):
                    if not isinstance(item, dict):
                        raise ScenarioLoadError(
                            f"{path}.{shortcut}[{i}] must be a condition object "
                            f"(got {type(item).__name__})"
                        )
                children_list = payload
            children = tuple(
                self._parse_scenario_event_condition(
                    c, mapper, path=f"{path}.{shortcut}[{i}]",
                )
                for i, c in enumerate(children_list)
            )
            return ScenarioEventCondition(condition_type=target_type, children=children)

        ctype = str(raw["condition_type"])
        # 合成条件 (NOT / AND / OR): children を再帰パース
        if ctype in {"NOT", "AND", "OR"}:
            children_raw = raw.get("children", [])
            if not isinstance(children_raw, list):
                raise ScenarioLoadError(
                    f"{path}: {ctype} condition.children must be a list "
                    f"(got {type(children_raw).__name__})"
                )
            children = tuple(
                self._parse_scenario_event_condition(
                    c, mapper, path=f"{path}.children[{i}]",
                )
                for i, c in enumerate(children_raw)
            )
            return ScenarioEventCondition(condition_type=ctype, children=children)
        # leaf 条件
        spot_id = None
        if raw.get("target_spot"):
            spot_id = mapper.get_int("spot", raw["target_spot"])
        object_id = None
        if raw.get("target_object"):
            object_id = mapper.get_int("object", raw["target_object"])
        item_spec_id = None
        if raw.get("required_item"):
            item_spec_id = mapper.get_int("item_spec", raw["required_item"])
        return ScenarioEventCondition(
            condition_type=ctype,
            tick=raw.get("tick"),
            tick_start=raw.get("tick_start"),
            tick_end=raw.get("tick_end"),
            flag_name=raw.get("flag_name"),
            spot_id=spot_id,
            object_id=object_id,
            required_state=raw.get("required_state"),
            item_spec_id=item_spec_id,
            tick_modulo=raw.get("tick_modulo"),
            tick_phase=raw.get("tick_phase"),
            weather_type=raw.get("weather_type"),
            state_key=raw.get("state_key"),
            ticks_offset=raw.get("ticks_offset"),
            # JSON の `true` / `false` 以外（数値の 1 / 文字列 "true" など）は
            # 暗黙の coercion を避けて作家ミスとして弾く。
            treat_missing_as_passed=raw.get("treat_missing_as_passed", False) is True,
        )

    def _parse_reactive_passage_bindings(
        self, raw: Dict[str, Any], mapper: ScenarioIdMapper,
    ) -> Tuple[ReactivePassageBinding, ...]:
        """`reactive_bindings.passages` を Passage 用 binding にパースする。

        スキーマ:
          "reactive_bindings": {
            "passages": [
              {
                "target": "<connection_string_id>",
                "predicate": <ScenarioEventCondition tree>,
                "on_true_state": "OPEN",
                "on_false_state": "LOCKED"
              }
            ]
          }
        """
        if not isinstance(raw, dict):
            return ()
        passages_raw = raw.get("passages", [])
        if not isinstance(passages_raw, list):
            raise ScenarioLoadError(
                f"reactive_bindings.passages must be a list "
                f"(got {type(passages_raw).__name__})"
            )
        bindings: list[ReactivePassageBinding] = []
        for i, b in enumerate(passages_raw):
            target = b.get("target")
            if not target:
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].target is required"
                )
            cid = mapper.get_int("connection", target)
            predicate_raw = b.get("predicate")
            if not isinstance(predicate_raw, dict):
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].predicate must be an object"
                )
            predicate = self._parse_scenario_event_condition(
                predicate_raw, mapper,
                path=f"reactive_bindings.passages[{i}].predicate",
            )
            on_true = b.get("on_true_state")
            on_false = b.get("on_false_state")
            if not on_true:
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].on_true_state is required"
                )
            if not on_false:
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].on_false_state is required"
                )
            apply_to_reverse = bool(b.get("apply_to_reverse", True))
            bindings.append(
                ReactivePassageBinding(
                    target_connection_id=ConnectionId.create(cid),
                    predicate=predicate,
                    on_true_state=str(on_true),
                    on_false_state=str(on_false),
                )
            )
            # bidirectional 接続には自動で逆方向 binding を生やす（既定）。
            # 一方通行で良い場合は apply_to_reverse=false を明示する。
            reverse_str = f"{target}__reverse"
            if apply_to_reverse and mapper.contains("connection", reverse_str):
                rev_cid = mapper.get_int("connection", reverse_str)
                bindings.append(
                    ReactivePassageBinding(
                        target_connection_id=ConnectionId.create(rev_cid),
                        predicate=predicate,
                        on_true_state=str(on_true),
                        on_false_state=str(on_false),
                    )
                )
        return tuple(bindings)

    def _parse_reactive_object_state_bindings(
        self, raw: Dict[str, Any], mapper: ScenarioIdMapper,
    ) -> Tuple[ReactiveObjectStateBinding, ...]:
        """`reactive_bindings.objects` を ReactiveObjectStateBinding にパース。

        スキーマ:
          "reactive_bindings": {
            "objects": [
              {
                "target": "<object_string_id>",
                "predicate": <ScenarioEventCondition tree>,
                "on_true_state_updates": {"k": v, ...},
                "on_false_state_updates": {"k": v, ...}
              }
            ]
          }
        """
        if not isinstance(raw, dict):
            return ()
        objects_raw = raw.get("objects", [])
        if not isinstance(objects_raw, list):
            raise ScenarioLoadError(
                f"reactive_bindings.objects must be a list "
                f"(got {type(objects_raw).__name__})"
            )
        out: list[ReactiveObjectStateBinding] = []
        for i, b in enumerate(objects_raw):
            target = b.get("target")
            if not target:
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].target is required"
                )
            oid = mapper.get_int("object", target)
            predicate_raw = b.get("predicate")
            if not isinstance(predicate_raw, dict):
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].predicate must be an object"
                )
            predicate = self._parse_scenario_event_condition(
                predicate_raw, mapper,
                path=f"reactive_bindings.objects[{i}].predicate",
            )
            on_true = b.get("on_true_state_updates", {})
            on_false = b.get("on_false_state_updates", {})
            if not isinstance(on_true, dict) or not isinstance(on_false, dict):
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].on_true/false_state_updates must be objects"
                )
            out.append(
                ReactiveObjectStateBinding(
                    target_object_id=SpotObjectId.create(oid),
                    predicate=predicate,
                    on_true_state_updates=tuple((k, v) for k, v in on_true.items()),
                    on_false_state_updates=tuple((k, v) for k, v in on_false.items()),
                )
            )
        return tuple(out)

    def _parse_synchronized_action_groups(
        self, raw: Any, mapper: ScenarioIdMapper,
    ) -> Tuple[SynchronizedActionGroup, ...]:
        """`synchronized_action_groups` を SynchronizedActionGroup 値オブジェクト
        の tuple にパースする。

        スキーマ:
          [
            {
              "id": "vault_unlock",
              "required_action_ids": ["pull_lever_left", "pull_lever_right"],
              "window_ticks": 2,
              "on_complete": [<InteractionEffect>...],
              "on_timeout": [<InteractionEffect>...],
              "on_prepare_observation_message": "..."
            }
          ]
        """
        if not isinstance(raw, list):
            return ()
        out: list[SynchronizedActionGroup] = []
        for i, g in enumerate(raw):
            if not isinstance(g, dict):
                raise ScenarioLoadError(
                    f"synchronized_action_groups[{i}] must be an object"
                )
            gid = g.get("id")
            if not gid:
                raise ScenarioLoadError(
                    f"synchronized_action_groups[{i}].id is required"
                )
            req = g.get("required_action_ids", [])
            if not isinstance(req, list):
                raise ScenarioLoadError(
                    f"synchronized_action_groups[{i}].required_action_ids must be a list"
                )
            on_complete = tuple(
                self._parse_interaction_effect(e, mapper)
                for e in g.get("on_complete", [])
            )
            on_timeout = tuple(
                self._parse_interaction_effect(e, mapper)
                for e in g.get("on_timeout", [])
            )
            out.append(
                SynchronizedActionGroup(
                    group_id=str(gid),
                    required_action_ids=tuple(str(x) for x in req),
                    window_ticks=int(g.get("window_ticks", 1)),
                    on_complete=on_complete,
                    on_timeout=on_timeout,
                    on_prepare_observation_message=g.get("on_prepare_observation_message"),
                )
            )
        return tuple(out)

    def _parse_weather_config(self, raw: Dict[str, Any]) -> Optional[ScenarioWeatherConfig]:
        weather = raw.get("weather") if isinstance(raw, dict) else None
        if not isinstance(weather, dict):
            return None
        enabled = bool(weather.get("enabled", False))
        initial = weather.get("initial", {})
        if not isinstance(initial, dict):
            initial = {}
        weather_type = WeatherTypeEnum[str(initial.get("weather_type", "FOG"))]
        intensity = float(initial.get("intensity", 0.6))
        return ScenarioWeatherConfig(
            enabled=enabled,
            initial_state=WeatherState(weather_type=weather_type, intensity=intensity),
            update_interval_ticks=int(weather.get("update_interval_ticks", 6)),
            announce_changes=bool(weather.get("announce_changes", True)),
        )

    def _parse_discoverable_item(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> DiscoverableItem:
        item_sid = raw["item_spec"]
        dc = self._parse_discovery_condition(raw.get("discovery_condition", {}), mapper)
        return DiscoverableItem(
            item_spec_id=ItemSpecId.create(mapper.get_int("item_spec", item_sid)),
            discovery_condition=dc,
            is_discovered=False,
            description=raw.get("description", ""),
        )

    def _parse_discovery_condition(self, raw: Optional[Dict[str, Any]], mapper: ScenarioIdMapper) -> DiscoveryCondition:
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

    def _parse_passage_condition(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> PassageCondition:
        item_sid = raw.get("required_item")
        item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
        return PassageCondition(
            condition_type=PassageConditionTypeEnum[raw["condition_type"]],
            item_spec_id=item_spec_id,
            flag_name=raw.get("flag_name"),
            consume_item=bool(raw.get("consume_item", False)),
            failure_message=raw.get("failure_message", ""),
        )

    def _parse_connections(
        self, conns_raw: List[Dict[str, Any]], graph: SpotGraphAggregate, mapper: ScenarioIdMapper,
    ) -> None:
        for c in conns_raw:
            cid = mapper.register("connection", c["id"])
            from_sid = mapper.get_int("spot", c["from"])
            to_sid = mapper.get_int("spot", c["to"])
            conditions = [self._parse_passage_condition(p, mapper) for p in c.get("passage_conditions", [])]
            is_bidir = bool(c.get("is_bidirectional", True))
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

    def _parse_players(
        self, players_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> List[PlayerSpawnConfig]:
        spawns: List[PlayerSpawnConfig] = []
        for p in players_raw:
            pid = mapper.register("player", p["id"])
            spot_sid = p["spawn_spot"]
            spot_id = SpotId.create(mapper.get_int("spot", spot_sid))
            items = tuple(
                ItemSpecId.create(mapper.get_int("item_spec", i))
                for i in p.get("initial_items", [])
            )
            spawns.append(PlayerSpawnConfig(
                string_id=p["id"],
                player_id=pid,
                name=p["name"],
                spawn_spot_id=spot_id,
                initial_item_spec_ids=items,
            ))
        return spawns

    def _parse_end_conditions(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
    ) -> List[GameEndCondition]:
        if not raw:
            return []
        items = raw if isinstance(raw, list) else [raw]
        conditions: List[GameEndCondition] = []
        for item in items:
            ctype = GameEndConditionTypeEnum[item["type"]]
            target_spot = None
            if "target_spot" in item:
                target_spot = SpotId.create(mapper.get_int("spot", item["target_spot"]))
            conditions.append(GameEndCondition(
                condition_type=ctype,
                target_spot_id=target_spot,
                target_flag=item.get("target_flag"),
                tick_limit=item.get("tick_limit"),
            ))
        return conditions
