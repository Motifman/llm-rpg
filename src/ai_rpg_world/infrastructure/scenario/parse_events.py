"""scenario events / reactive bindings / sync groups の読み取り。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import PlayerOutcomeRuleValidationException
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import PlayerOutcomeRule
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import ReactiveObjectStateBinding
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import ReactivePassageBinding
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    SUPPORTED_CONDITION_TYPES,
    ScenarioEventCondition,
    ScenarioEventConditionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import SynchronizedActionGroup
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    declared_action_names,
    iter_mappings,
    optional_spot_id,
    parse_bool,
)
from ai_rpg_world.infrastructure.scenario.parse_interactions import (
    parse_interaction_condition,
    parse_interaction_def,
    parse_interaction_effect,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import (
    ScenarioIdMapper,
    ScenarioIdMappingError,
)
from ai_rpg_world.infrastructure.scenario.validate_features import (
    SILENT_REACTIVE_OBJECT_BINDING_WARNING,
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
        effects = tuple(
            parse_interaction_effect(
                e, mapper, actor_context="scenario_event",
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

def parse_reactive_passage_bindings( raw: Dict[str, Any], mapper: ScenarioIdMapper,
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
        predicate = parse_scenario_event_condition(
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
        apply_to_reverse = parse_bool(
            b.get("apply_to_reverse", True),
            path=f"reactive_bindings.passages[{i}].apply_to_reverse",
        )
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

def parse_reactive_object_state_bindings( raw: Dict[str, Any], mapper: ScenarioIdMapper,
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
        predicate = parse_scenario_event_condition(
            predicate_raw, mapper,
            path=f"reactive_bindings.objects[{i}].predicate",
        )
        on_true = b.get("on_true_state_updates", {})
        on_false = b.get("on_false_state_updates", {})
        if not isinstance(on_true, dict) or not isinstance(on_false, dict):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].on_true/false_state_updates must be objects"
            )
        # 著者が宣言した観測 narrative (オプショナル)。flip 方向ごとに別文。
        # 例: 採取資源 cooldown reset (false→true) には narrative_on_true=
        # "ベリーの茂みに新しい実が生っている" を渡す。
        narrative_on_true = b.get("narrative_on_true")
        narrative_on_false = b.get("narrative_on_false")
        if narrative_on_true is not None and not isinstance(narrative_on_true, str):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].narrative_on_true must be a string"
            )
        if narrative_on_false is not None and not isinstance(narrative_on_false, str):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].narrative_on_false must be a string"
            )
        # #383: どちらの向きにも narrative が無い binding は、状態だけ静かに
        # 変わって誰にも観測されない。formatter は narrative 無しなら観測を
        # 出さない (#372) ので、**著者の書き忘れと意図的な無音が区別できない**。
        #
        # 「向きごとに無ければ警告」にはしない。実測するとその形は 59 件警告し、
        # うち 48 件が survival_island_v2 / v2_short / v3_coop / v4_coop から出る。
        # それらは全部 on_false (= 自分の採取で資源が枯れた) で、interact の
        # 結果として本人に伝わっているので narrative を書かないのが正しい。
        # ノイズを出すと人が警告を無視するようになり、検出器が死ぬ。
        #
        # 片方でも書いてあれば著者はこの仕組みを知っていて、もう片方を意図的に
        # 省いたと読める。**書き忘れの信号は「どこにも観測が無い」。**
        #
        # 空文字は「意図的な無音」の明示とみなして警告しない (`is None` で
        # 判定する)。formatter 上の挙動は narrative 無しと同じ。
        #
        # 状態更新の有無は見ない。ReactiveObjectStateBinding が「どちらかの
        # 向きに状態更新がある」ことを不変条件として持つので、ここに来る
        # binding は必ず何かを変える (テストでこの前提を固定している)。
        if narrative_on_true is None and narrative_on_false is None:
            logging.getLogger(__name__).warning(
                "[%s] reactive_bindings.objects[%d] target=%s は状態を変えるが "
                "narrative_on_true / narrative_on_false のどちらも無いため、"
                "変化が誰にも観測されない。意図的な無音なら "
                'narrative_on_true="" を明示してください。',
                SILENT_REACTIVE_OBJECT_BINDING_WARNING, i, target,
            )
        out.append(
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(oid),
                predicate=predicate,
                on_true_state_updates=tuple((k, v) for k, v in on_true.items()),
                on_false_state_updates=tuple((k, v) for k, v in on_false.items()),
                narrative_on_true=narrative_on_true,
                narrative_on_false=narrative_on_false,
            )
        )
    return tuple(out)

def parse_player_interactions( raw_list: Any, mapper: ScenarioIdMapper,
) -> Tuple[InteractionDef, ...]:
    """シナリオ直下の ``player_interactions`` をパースする。

    対人行為は spot object ではなくシナリオに 1 回だけ宣言し、「どこで
    使えるか」は前提条件 (spot / 明るさ / 持ち物 / 役割) で表現する。
    紐付けを成立条件の代用にすると、同じ行為を複数の場所で使うのに複数回
    定義が要り、「暗い場所ならどこでも」のような動的な条件も書けない。
    """
    if not raw_list:
        return ()
    if not isinstance(raw_list, list):
        raise ScenarioLoadError("player_interactions must be a list")

    parsed: list[InteractionDef] = []
    seen_action_names: set[str] = set()
    for i, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"player_interactions[{i}] must be an object"
            )
        action_name = raw.get("action_name")
        if not isinstance(action_name, str) or not action_name.strip():
            raise ScenarioLoadError(
                f"player_interactions[{i}] requires a non-empty action_name"
            )
        action_name = action_name.strip()
        if action_name in seen_action_names:
            # LLM は action_name で行為を指定するので、重複すると
            # 「どちらが実行されたか分からない」状態になる。
            raise ScenarioLoadError(
                f"duplicate player_interaction action_name: {action_name!r}"
            )
        seen_action_names.add(action_name)

        idef = parse_interaction_def(
            raw, mapper, allow_target_notification=True
        )
        if not any(
            e.target is EffectTarget.TARGET_PLAYER for e in idef.effects
        ):
            # 対象への効果を 1 つも持たない定義は書き間違い。放置すると
            # 「相手を選んだのに自分に効く」という最も分かりにくい失敗になる。
            raise ScenarioLoadError(
                f"player_interaction {action_name!r} has no effect with "
                "target=TARGET_PLAYER. 対人行為は相手に効く効果を 1 つ以上"
                "持つ必要があります"
            )
        parsed.append(idef)
    return tuple(parsed)

def reject_unreachable_synchronized_action_names(
    groups: Tuple[SynchronizedActionGroup, ...],
    raw: Dict[str, Any],
) -> None:
    """`required_action_names` が到達可能な名前を指していることを確かめる。

    ## なぜ読み込み時に落とすか (#853)

    改称前、`sync_levers_demo` は `required_action_ids` に
    `["pull_lever_left", "pull_lever_right"]` と書いていたのに、レバーの
    `interactions` は**両方とも空配列**だった。つまり **その名前はプロンプトの
    どこにも現れない**。エージェントは表示されていないものを指定するしかなく、
    推測した名前は (改称前の handler では) `success=True` で返っていた。

    「宣言はあるが到達できない」は実行時には静かに失敗する。#843 で終了条件の
    必須フィールド欠落を読み込み時に落としたのと同じ発想で、**宣言した時点で**
    落とす。

    ## 何を到達可能とみなすか

    - spot の `interior.objects[].interactions[].action_name`
    - connection の `interactions[].action_name`
    - シナリオ直下の `player_interactions[].action_name`

    いずれもプロンプトの「使える操作」に出る経路を持つ。前提条件で出ない場合は
    あるが、**宣言が存在しないことと、条件で今出ていないことは別**なので、ここでは
    宣言の有無だけを見る。
    """
    if not groups:
        return
    declared = declared_action_names(raw)
    unreachable: List[str] = []
    for group in groups:
        for name in group.required_action_names:
            if name not in declared:
                unreachable.append(f"{group.group_id}.{name}")
    if unreachable:
        raise ScenarioLoadError(
            "synchronized_action_groups の required_action_names に、"
            "どこにも宣言されていない操作名があります: "
            f"{unreachable}。"
            " interactions[].action_name として宣言しないと、"
            "プロンプトに表示されずエージェントが指定できません。"
            f" 宣言済みの名前: {sorted(declared)}"
        )

def parse_synchronized_action_groups( raw: Any, mapper: ScenarioIdMapper,
) -> Tuple[SynchronizedActionGroup, ...]:
    """`synchronized_action_groups` を SynchronizedActionGroup 値オブジェクト
    の tuple にパースする。

    スキーマ:
      [
        {
          "id": "vault_unlock",
          "required_action_names": ["pull_lever_left", "pull_lever_right"],
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
        # #853: 旧キー `required_action_ids` を黙って無視しない。
        #
        # 名前で指す方針 (design_decisions #3) に寄せて改称した。知らないキーを
        # 無視すると「書いたのに効かない」= 静かな失敗になるので、明示的に落とす。
        if "required_action_ids" in g:
            raise ScenarioLoadError(
                f"synchronized_action_groups[{i}].required_action_ids は"
                f" required_action_names へ改称されました。値は"
                f" interactions[].action_name として宣言済みの名前を書きます"
                f" (内部 ID ではありません)。"
            )
        req = g.get("required_action_names", [])
        if not isinstance(req, list):
            raise ScenarioLoadError(
                f"synchronized_action_groups[{i}].required_action_names must be a list"
            )
        on_complete = tuple(
            parse_interaction_effect(
                e, mapper, actor_context="synchronized_action_group",
            )
            for e in g.get("on_complete", [])
        )
        on_timeout = tuple(
            parse_interaction_effect(
                e, mapper, actor_context="synchronized_action_group",
            )
            for e in g.get("on_timeout", [])
        )
        out.append(
            SynchronizedActionGroup(
                group_id=str(gid),
                required_action_names=tuple(str(x) for x in req),
                window_ticks=int(g.get("window_ticks", 1)),
                on_complete=on_complete,
                on_timeout=on_timeout,
                on_prepare_observation_message=g.get("on_prepare_observation_message"),
            )
        )
    return tuple(out)

