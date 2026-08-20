"""scenario events と event condition の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import PlayerOutcomeRuleValidationException
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import PlayerOutcomeRule
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    SUPPORTED_CONDITION_TYPES,
    ScenarioEventCondition,
    ScenarioEventConditionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.infrastructure.scenario.declaration_site import declaring
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    optional_spot_id,
    parse_bool,
)
from ai_rpg_world.infrastructure.scenario.parse_interaction_effects import (
    parse_interaction_effect,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import (
    ScenarioIdMapper,
    ScenarioIdMappingError,
)
from ai_rpg_world.infrastructure.scenario.validate_features import (
    _SCENARIO_EVENT_RECIPIENTS,
    _SCENARIO_EVENT_TRIGGERS,
)

_COMPOSITE_SUGAR: Dict[str, str] = {
    "all_of": "AND",
    "any_of": "OR",
    "not_": "NOT",
}

def parse_scenario_events(
    events_raw: Sequence[Dict[str, Any]],
    mapper: ScenarioIdMapper,
    *,
    player_attribute_specs: PlayerAttributeSpecs,
) -> Tuple[ScenarioEventDef, ...]:
    if not isinstance(events_raw, list):
        raise ScenarioLoadError("scenario_events must be a list")
    event_ids: set[str] = set()
    for index, raw in enumerate(events_raw):
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"scenario_events[{index}] must be an object"
            )
        event_id = raw.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ScenarioLoadError(
                f"scenario_events[{index}].id must be a non-empty string"
            )
        if event_id in event_ids:
            raise ScenarioLoadError(
                f"scenario_events has duplicate event id: {event_id!r}"
            )
        event_ids.add(event_id)

    parsed: list[ScenarioEventDef] = []
    for index, raw in enumerate(events_raw):
        observation = raw.get("observation", {})
        if not isinstance(observation, dict):
            raise ScenarioLoadError(
                f"scenario_events[{index}].observation must be an object"
            )
        event_id = raw["id"]
        trigger = raw.get("trigger", "ON_TICK")
        if (
            not isinstance(trigger, str)
            or trigger not in _SCENARIO_EVENT_TRIGGERS
        ):
            raise ScenarioLoadError(
                f"scenario_event[{event_id}].trigger has unknown value "
                f"{trigger!r}; valid values: {sorted(_SCENARIO_EVENT_TRIGGERS)}"
            )
        recipients = observation.get("recipients", "all_players")
        if (
            not isinstance(recipients, str)
            or recipients not in _SCENARIO_EVENT_RECIPIENTS
        ):
            raise ScenarioLoadError(
                f"scenario_event[{event_id}].observation.recipients has unknown "
                f"value {recipients!r}; valid values: "
                f"{sorted(_SCENARIO_EVENT_RECIPIENTS)}"
            )
        target_spot = observation.get("target_spot")
        if recipients == "players_at_spot" and not target_spot:
            raise ScenarioLoadError(
                f"scenario_event[{event_id}] with recipients=players_at_spot "
                "requires observation.target_spot"
            )
        next_event_id = raw.get("next_event_id")
        if next_event_id is not None:
            if not isinstance(next_event_id, str) or next_event_id not in event_ids:
                raise ScenarioLoadError(
                    f"scenario_event[{event_id}].next_event_id references unknown "
                    f"event: {next_event_id!r}"
                )
        delay_ticks = raw.get("delay_ticks", 0)
        if (
            not isinstance(delay_ticks, int)
            or isinstance(delay_ticks, bool)
            or delay_ticks < 0
        ):
            raise ScenarioLoadError(
                f"scenario_event[{event_id}].delay_ticks must be a "
                f"non-negative integer, got {delay_ticks!r}"
            )
        conditions = tuple(
            parse_scenario_event_condition(
                c, mapper, path=f"scenario_event[{event_id}].conditions[{i}]",
            )
            for i, c in enumerate(raw.get("conditions", []))
        )
        with declaring(f"scenario_event {event_id!r} の効果:"):
            effects = tuple(
                parse_interaction_effect(
                    e,
                    mapper,
                    actor_context="scenario_event",
                    player_attribute_specs=player_attribute_specs,
                )
                for e in raw.get("effects", [])
            )
        parsed.append(
            ScenarioEventDef(
                event_id=event_id,
                trigger=trigger,
                once=parse_bool(
                    raw.get("once", True),
                    path=f"scenario_event[{event_id}].once",
                ),
                conditions=conditions,
                effects=effects,
                observation_category=str(observation.get("category", "environment")),
                recipients=recipients,
                target_spot_id=optional_spot_id(target_spot, mapper),
                schedules_turn=parse_bool(
                    observation.get("schedules_turn", True),
                    path=(
                        f"scenario_event[{event_id}].observation.schedules_turn"
                    ),
                ),
                breaks_movement=parse_bool(
                    observation.get("breaks_movement", False),
                    path=(
                        f"scenario_event[{event_id}].observation.breaks_movement"
                    ),
                ),
                next_event_id=next_event_id,
                delay_ticks=delay_ticks,
            )
        )
    return tuple(parsed)

def parse_player_outcome_rules(
    raw_rules: Any,
    mapper: ScenarioIdMapper,
) -> Tuple[PlayerOutcomeRule, ...]:
    """個人結果規則を既存の ScenarioEventCondition AST へ変換する。"""
    if not isinstance(raw_rules, list):
        raise ScenarioLoadError("player_outcome_rules must be a list")

    parsed: list[PlayerOutcomeRule] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_rules):
        path = f"player_outcome_rules[{index}]"
        if not isinstance(raw, dict):
            raise ScenarioLoadError(f"{path} must be an object")

        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ScenarioLoadError(f"{path}.id must be a non-empty string")
        if rule_id in seen_ids:
            raise ScenarioLoadError(
                f"player_outcome_rules id {rule_id!r} が重複しています"
            )
        seen_ids.add(rule_id)

        trigger_raw = raw.get("trigger")
        if not isinstance(trigger_raw, dict):
            raise ScenarioLoadError(f"{path}.trigger must be a condition object")
        player_conditions_raw = raw.get("player_conditions")
        if not isinstance(player_conditions_raw, list):
            raise ScenarioLoadError(f"{path}.player_conditions must be a list")
        for condition_index, condition_raw in enumerate(player_conditions_raw):
            if not isinstance(condition_raw, dict):
                raise ScenarioLoadError(
                    f"{path}.player_conditions[{condition_index}] must be a "
                    "condition object"
                )

        once = raw.get("once")
        if not isinstance(once, bool):
            raise ScenarioLoadError(f"{path}.once must be an explicit boolean")

        outcome_raw = raw.get("outcome")
        try:
            outcome = PlayerOutcomeEnum(outcome_raw)
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"{path}.outcome is unknown: {outcome_raw!r}"
            ) from exc

        try:
            parsed.append(
                PlayerOutcomeRule(
                    rule_id=rule_id,
                    trigger=parse_scenario_event_condition(
                        trigger_raw,
                        mapper,
                        path=f"{path}.trigger",
                    ),
                    player_conditions=tuple(
                        parse_scenario_event_condition(
                            condition_raw,
                            mapper,
                            path=(
                                f"{path}.player_conditions[{condition_index}]"
                            ),
                        )
                        for condition_index, condition_raw in enumerate(
                            player_conditions_raw
                        )
                    ),
                    outcome=outcome,
                    once=once,
                )
            )
        except PlayerOutcomeRuleValidationException as exc:
            raise ScenarioLoadError(f"{path}: {exc}") from exc
    return tuple(parsed)

def parse_scenario_event_condition(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    path: str = "condition",
) -> ScenarioEventCondition:
    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            f"{path} must be a condition object "
            f"(got {type(raw).__name__})"
        )
    # ---- 糖衣記法を従来形に正規化 ----
    # `all_of: [...]` / `any_of: [...]` / `not_: <cond>` の
    # いずれかが存在すれば `condition_type` + `children` 形に変換する。
    # `condition_type` と糖衣記法が同時にあるのは作家ミスとして拒否。
    sugar_keys = [k for k in _COMPOSITE_SUGAR if k in raw]
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
        target_type = _COMPOSITE_SUGAR[shortcut]
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
            parse_scenario_event_condition(
                c, mapper, path=f"{path}.{shortcut}[{i}]",
            )
            for i, c in enumerate(children_list)
        )
        try:
            return ScenarioEventCondition(
                condition_type=target_type,
                children=children,
            )
        except ScenarioEventConditionValidationException as exc:
            raise ScenarioLoadError(f"{path}: {exc}") from exc

    ctype = raw.get("condition_type")
    if not isinstance(ctype, str):
        raise ScenarioLoadError(
            f"{path}.condition_type must be a string, got {ctype!r}"
        )
    # 綴り間違いはここで落とす。**通すと永久に発火しない出来事になる。**
    #
    # 評価器は知らない種類を False に落とすので、読み込みが通った時点で
    # 誰も気づけなくなる。妨害のように条件を大量に書く機能では、1 文字の
    # 違いが「なぜか何も起きない」になる。
    if ctype not in SUPPORTED_CONDITION_TYPES:
        raise ScenarioLoadError(
            f"{path}: unknown condition_type {ctype!r}; valid values: "
            f"{sorted(SUPPORTED_CONDITION_TYPES)}"
        )
    if ctype == "GAME_PHASE_IS":
        game_phase = raw.get("game_phase")
        known_phases = {phase.value for phase in GamePhase}
        if not isinstance(game_phase, str) or game_phase not in known_phases:
            raise ScenarioLoadError(
                f"{path}.game_phase must be one of "
                f"{', '.join(sorted(known_phases))}"
            )
    if ctype == "WEATHER_IS":
        weather_type = raw.get("weather_type")
        if weather_type is None:
            raise ScenarioLoadError(
                f"{path}.weather_type is required for WEATHER_IS"
            )
        if not isinstance(weather_type, str):
            raise ScenarioLoadError(
                f"{path}.weather_type must be a string, got {weather_type!r}"
            )
        known_weather_types = {weather.value for weather in WeatherTypeEnum}
        if weather_type not in known_weather_types:
            raise ScenarioLoadError(
                f"{path}.weather_type has unknown value {weather_type!r}; "
                f"valid values: {sorted(known_weather_types)}"
            )
    if ctype == "PLAYERS_AT_SPOT":
        if not raw.get("target_spot"):
            raise ScenarioLoadError(
                f"{path}.target_spot is required for PLAYERS_AT_SPOT"
            )
        required_player_count = raw.get("required_player_count")
        if required_player_count is not None and (
            isinstance(required_player_count, bool)
            or not isinstance(required_player_count, int)
            or required_player_count <= 0
        ):
            raise ScenarioLoadError(
                f"{path}.required_player_count must be a positive integer"
            )
    # 合成条件 (NOT / AND / OR): children を再帰パース
    if ctype in {"NOT", "AND", "OR"}:
        children_raw = raw.get("children", [])
        if not isinstance(children_raw, list):
            raise ScenarioLoadError(
                f"{path}: {ctype} condition.children must be a list "
                f"(got {type(children_raw).__name__})"
            )
        children = tuple(
            parse_scenario_event_condition(
                c, mapper, path=f"{path}.children[{i}]",
            )
            for i, c in enumerate(children_raw)
        )
        try:
            return ScenarioEventCondition(
                condition_type=ctype,
                children=children,
            )
        except ScenarioEventConditionValidationException as exc:
            raise ScenarioLoadError(f"{path}: {exc}") from exc
    # leaf 条件
    try:
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
            required_player_count=raw.get("required_player_count"),
            game_phase=raw.get("game_phase"),
            object_id=object_id,
            required_state=raw.get("required_state"),
            item_spec_id=item_spec_id,
            tick_modulo=raw.get("tick_modulo"),
            tick_phase=raw.get("tick_phase"),
            weather_type=raw.get("weather_type"),
            state_key=raw.get("state_key"),
            ticks_offset=raw.get("ticks_offset"),
            # JSON の `true` / `false` 以外は作家ミスとして弾く。
            treat_missing_as_passed=parse_bool(
                raw.get("treat_missing_as_passed", False),
                path=f"{path}.treat_missing_as_passed",
            ),
            # None 許容で他 condition_type では無視される。範囲チェックは
            # ScenarioEventCondition.__post_init__ に任せる。
            probability=(
                float(raw["probability"])
                if raw.get("probability") is not None
                else None
            ),
        )
    except ScenarioLoadError:
        raise
    except (
        ScenarioEventConditionValidationException,
        ScenarioIdMappingError,
        TypeError,
        ValueError,
    ) as exc:
        raise ScenarioLoadError(f"{path}: {exc}") from exc
