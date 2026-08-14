"""シナリオ定義 JSON → ドメインオブジェクト変換。

scenario_format_version "1.0" に対応。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from string import Formatter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ai_rpg_world.application.llm.tool_exposure import ToolExposure

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ExpEffect,
    GoldEffect,
    DamageHpEffect,
    HealEffect,
    ItemEffect,
    RecoverMpEffect,
    ReviveEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterTemplateValidationException,
)
from ai_rpg_world.domain.monster.value_object.attack_status_effect_chance import (
    AttackStatusEffectChance,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.death_semantics import DeathSemantics
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    ITEM_ACTION_NAME_PREFIX,
    RESERVED_ACTION_NAME_PREFIX,
)
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)
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
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    CALL_MEETING_EFFECT_TRIGGERS,
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import (
    PlayerOutcomeRule,
)
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
    SUPPORTED_CONDITION_TYPES,
    ScenarioEventCondition,
    ScenarioEventConditionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
    state_display_value_identity,
)
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PlayerOutcomeRuleValidationException,
    StateDisplayRuleValidationException,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import (
    ScenarioIdMapper,
    ScenarioIdMappingError,
)

#: 「状態を変えるのに観測を一切出さない object binding」の警告を指す識別子。
#:
#: 警告文そのものではなく**この定数で照合させるため**に置く。テストが警告文の
#: 部分文字列 ("narrative" 等) で照合していると、文言を書き換えた瞬間に
#: 「警告が出ないこと」を見る試験が全部空振りになる。レビューで実証された:
#: 文言から「narrative」の語を消して判定を過剰側へ広げると、主要実験シナリオに
#: 48 件のノイズ警告が出ている状態で全部緑になった。
#:
#: `test_scenario_loader.py` と
#: `test_shipped_scenarios_have_no_silent_bindings.py` がこの定数を import して
#: 照合する。**文言は自由に変えてよいが、この定数を warning から外すと正の
#: 試験が落ちる。**
SILENT_REACTIVE_OBJECT_BINDING_WARNING = "silent_reactive_object_binding"

_DAY_NIGHT_FEATURE = "day_night"
_WEATHER_FEATURE = "weather"

# 新しい interaction 条件を足したとき、その条件が環境機能を要求するかを必ず
# 判断させる。判定側もこの表を読むため、検査と実装の対象集合が分岐しない。
_INTERACTION_CONDITION_FEATURE_REQUIREMENTS: Mapping[
    InteractionConditionTypeEnum, Optional[str]
] = {
    InteractionConditionTypeEnum.ALWAYS: None,
    InteractionConditionTypeEnum.HAS_ITEM: None,
    InteractionConditionTypeEnum.OBJECT_STATE: None,
    InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST: None,
    InteractionConditionTypeEnum.FLAG_SET: None,
    InteractionConditionTypeEnum.FLAG_NOT_SET: None,
    InteractionConditionTypeEnum.PLAYERS_AT_SPOT: None,
    InteractionConditionTypeEnum.PREPARED_ACTION: None,
    InteractionConditionTypeEnum.PUZZLE_INPUT_MATCH: None,
    InteractionConditionTypeEnum.HAS_ITEMS: None,
    InteractionConditionTypeEnum.ITEM_INSTANCE_STATE: None,
    InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE: None,
    InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST: None,
    InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW: None,
    InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST: None,
    InteractionConditionTypeEnum.PLAYER_STATE_IS: None,
    InteractionConditionTypeEnum.TIME_OF_DAY_IS: _DAY_NIGHT_FEATURE,
    InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT: _DAY_NIGHT_FEATURE,
    InteractionConditionTypeEnum.WEATHER_IS: _WEATHER_FEATURE,
    InteractionConditionTypeEnum.WEATHER_IS_NOT: _WEATHER_FEATURE,
    InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST: None,
    InteractionConditionTypeEnum.TARGET_PLAYER_IS_INCAPACITATED: None,
    InteractionConditionTypeEnum.TARGET_HAS_ITEM: None,
    InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM: None,
    InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS: None,
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS: None,
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT: None,
    InteractionConditionTypeEnum.AT_SPOT_IS: None,
    InteractionConditionTypeEnum.AT_SPOT_IS_NOT: None,
}

# monster spawn_condition が受理するキーと、成立に必要な環境機能の単一真実源。
# parser も整合検査もこの表を使い、未知キーは黙って無視しない。
_MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS: Mapping[str, Optional[str]] = {
    "day_night_phases": _DAY_NIGHT_FEATURE,
    "required_flags": None,
    "forbidden_flags": None,
    "weather_types": _WEATHER_FEATURE,
}

# 終了条件は、置かれた配列が成立時の勝敗ラベルを決める。条件型を追加した人が
# 「勝敗あり / 中立」のどちらかを判断するまで loader が受理しないよう全件を列挙する。
_GAME_END_CONDITION_ALLOWED_SECTIONS: Mapping[
    GameEndConditionTypeEnum, frozenset[str]
] = {
    GameEndConditionTypeEnum.ALL_AT_SPOT: frozenset({"win", "lose"}),
    GameEndConditionTypeEnum.ANY_AT_SPOT: frozenset({"win", "lose"}),
    GameEndConditionTypeEnum.FLAG_SET: frozenset({"win", "lose"}),
    GameEndConditionTypeEnum.TICK_LIMIT: frozenset({"win", "lose"}),
    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST: frozenset(
        {"win", "lose"}
    ),
    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE: (
        frozenset({"win", "lose"})
    ),
    GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST: frozenset({"win", "lose"}),
    GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED: frozenset({"end"}),
}

_SCENARIO_EVENT_TRIGGERS = frozenset({"ON_TICK", "ON_CHAIN"})
_SCENARIO_EVENT_RECIPIENTS = frozenset({"all_players", "players_at_spot"})


SUPPORTED_FORMAT_VERSIONS = ("1.0",)


class ScenarioLoadError(Exception):
    """シナリオ読み込み中のエラー。"""


def _parse_role_labels(raw: Any) -> Dict[str, str]:
    """``role_labels`` を読む。省略時は空 (呼び名を出さない)。"""
    value = raw.get("role_labels")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScenarioLoadError("metadata.role_labels はオブジェクトで書いてください")
    labels: Dict[str, str] = {}
    for key, label in value.items():
        if not isinstance(key, str) or not isinstance(label, str) or not label.strip():
            raise ScenarioLoadError(
                f"metadata.role_labels の要素は文字列で書いてください: {key!r}: {label!r}"
            )
        labels[key] = label.strip()
    return labels


def _parse_show_world_map(raw: Any) -> bool:
    """``show_world_map`` を読む。省略時は False (載せない)。

    真偽値以外は拒否する。``"true"`` と書いて常に真になると、書いた人の意図と
    結果が食い違う。
    """
    value = raw.get("show_world_map")
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ScenarioLoadError(
            f"metadata.show_world_map は true / false で書いてください: {value!r}"
        )
    return value


def _parse_bool(value: Any, *, path: str) -> bool:
    """JSON の真偽値だけを受理し、文字列や整数の暗黙変換を拒否する。"""
    if not isinstance(value, bool):
        raise ScenarioLoadError(
            f"{path} must be a boolean, got {value!r}"
        )
    return value


def _parse_player_outcome_messages(
    raw: Mapping[str, Any],
) -> Mapping[PlayerOutcomeEnum, str]:
    """終局結果ごとの観測文型を読み、置換可能な項目を限定する。"""
    value = raw.get("player_outcome_messages", {})
    if not isinstance(value, dict):
        raise ScenarioLoadError(
            "metadata.player_outcome_messages must be an object"
        )

    parsed: dict[PlayerOutcomeEnum, str] = {}
    for outcome_name, template_raw in value.items():
        path = f"metadata.player_outcome_messages.{outcome_name}"
        try:
            outcome = PlayerOutcomeEnum(outcome_name)
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"{path}: unknown player outcome {outcome_name!r}"
            ) from exc
        if outcome is PlayerOutcomeEnum.UNRESOLVED:
            raise ScenarioLoadError(f"{path}: UNRESOLVED cannot be announced")
        if not isinstance(template_raw, str) or not template_raw.strip():
            raise ScenarioLoadError(f"{path} must be a non-empty string")

        template = template_raw.strip()
        try:
            fields = [
                (field_name, format_spec, conversion)
                for _, field_name, format_spec, conversion in Formatter().parse(
                    template
                )
                if field_name is not None
            ]
        except ValueError as exc:
            raise ScenarioLoadError(f"{path}: invalid message template") from exc
        unknown = [name for name, _, _ in fields if name != "player_name"]
        if unknown:
            raise ScenarioLoadError(
                f"{path}: unknown placeholder {unknown[0]!r}; "
                "only {player_name} is allowed"
            )
        unsupported_format = [
            (name, format_spec, conversion)
            for name, format_spec, conversion in fields
            if format_spec or conversion is not None
        ]
        if unsupported_format:
            raise ScenarioLoadError(
                f"{path}: format specifiers and conversions are not allowed"
            )
        if not any(name == "player_name" for name, _, _ in fields):
            raise ScenarioLoadError(f"{path} must contain {{player_name}}")
        parsed[outcome] = template
    return parsed


def _parse_object_state_display(
    raw: Mapping[str, Any],
    *,
    recorded_tick_state_keys: frozenset[str] = frozenset(),
) -> Tuple[StateDisplayRule, ...]:
    """object.state_display を StateDisplayRule の列へ変換する。"""

    object_id = raw.get("id")
    raw_rules = raw.get("state_display", ())
    if raw_rules == ():
        return ()
    if not isinstance(raw_rules, list):
        raise ScenarioLoadError(f"object {object_id}.state_display must be a list")

    parsed: list[StateDisplayRule] = []
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(raw_rules):
        path = f"object {object_id}.state_display[{index}]"
        if not isinstance(item, dict):
            raise ScenarioLoadError(f"{path} must be an object")
        if "key" not in item:
            raise ScenarioLoadError(f"{path}.key is required")
        if "text" not in item:
            raise ScenarioLoadError(f"{path}.text is required")
        selectors = tuple(
            name for name in ("value", "at_least", "within_ticks") if name in item
        )
        if "within_ticks" in item and len(selectors) > 1:
            others = " and ".join(name for name in selectors if name != "within_ticks")
            raise ScenarioLoadError(
                f"{path} cannot specify both {others} and within_ticks"
            )
        if "value" in item and "at_least" in item:
            raise ScenarioLoadError(
                f"{path} cannot specify both value and at_least"
            )
        try:
            rule = StateDisplayRule(
                key=item["key"],
                value=item.get("value"),
                text=item["text"],
                at_least=item.get("at_least"),
                within_ticks=item.get("within_ticks"),
                requires_light=item.get("requires_light", False),
                unless_flag_set=item.get("unless_flag_set"),
            )
        except StateDisplayRuleValidationException as exc:
            raise ScenarioLoadError(f"{path}: {exc}") from exc
        if (
            rule.within_ticks is not None
            and rule.key not in recorded_tick_state_keys
        ):
            raise ScenarioLoadError(
                f"{path}.key={rule.key!r} must be written by this object's "
                "RECORD_OBJECT_STATE_TICK effect"
            )
        duplicate_key = (
            (rule.key, "within_ticks", rule.within_ticks)
            if rule.within_ticks is not None
            else (
                (rule.key, "at_least", rule.at_least)
                if rule.at_least is not None
                else (rule.key, "value", state_display_value_identity(rule.value))
            )
        )
        if duplicate_key in seen:
            raise ScenarioLoadError(
                f"{path} duplicates state_display rule for key={rule.key!r}"
            )
        seen.add(duplicate_key)
        parsed.append(rule)
    return tuple(parsed)


def _parse_object_hidden_state_keys(raw: Mapping[str, Any]) -> frozenset[str]:
    """object.hidden_state_keys を文字列集合へ変換する。"""

    object_id = raw.get("id")
    raw_keys = raw.get("hidden_state_keys", ())
    if raw_keys == ():
        return frozenset()
    if not isinstance(raw_keys, list):
        raise ScenarioLoadError(f"object {object_id}.hidden_state_keys must be a list")
    parsed: set[str] = set()
    for index, key in enumerate(raw_keys):
        if not isinstance(key, str) or not key.strip():
            raise ScenarioLoadError(
                f"object {object_id}.hidden_state_keys[{index}] must be a non-empty string"
            )
        parsed.add(key)
    return frozenset(parsed)


def _recorded_tick_state_keys(
    interactions: Any, own_object_id: int
) -> frozenset[str]:
    """この物体の操作が**自分に**書き込む「手番を記録する key」を集める。

    ``tick`` は世界の中に無い語 (#892)。世界の中の人が手番を数えているはずが
    ないので、記録用の key が prompt に出た時点で嘘になる。

    かつては ``visible_state`` が ``last_harvest_tick`` という**綴りを 1 つ
    直書き**して隠していた。流木や木の実はその名前を選んだので守られ、
    ``last_lit_tick`` と名付けた焚き火跡は守られずに漏れていた。

    守るのは名前ではなく「手番を記録する効果が書いた key」。名前は作家の
    自由で、engine が当てにいくものではない。

    シナリオ JSON に ``hidden_state_keys`` を書かせる案は採らない。書き忘れが
    即漏洩になる。``SpotObject.with_additional_hidden_state_keys`` の説明に
    「per-object 設定に頼ると設定漏れで漏れる (既知回帰)」とあり、同じ失敗を
    一度している。

    シナリオの ``target_object`` は、ここへ来る前に ``object_id`` (数値) へ
    読み替えられている。**自分自身を明示する書き方も多い** (``herb_planter``
    が ``target_object: herb_planter`` と書く形) ので、省略と同じものとして
    扱う。「指定があれば他所行き」と決めつけると、実際に多いほうの書き方を
    取りこぼす。

    ``object_id`` が**別の物体**を指す場合だけはここで拾えない。そちらは効果を
    適用する側が書き込みと同時に伏せる。
    """
    keys: set[str] = set()
    for interaction in interactions or ():
        for effect in getattr(interaction, "effects", ()) or ():
            if (
                getattr(effect, "effect_type", None)
                is not InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK
            ):
                continue
            params = getattr(effect, "parameters", None) or {}
            target = params.get("object_id")
            if target is not None and int(target) != int(own_object_id):
                continue
            state_key = params.get("state_key")
            if isinstance(state_key, str) and state_key:
                keys.add(state_key)
    return frozenset(keys)


def _remote_recorded_tick_state_keys(
    items_raw: Sequence[Mapping[str, Any]],
    mapper: ScenarioIdMapper,
) -> Mapping[int, frozenset[str]]:
    """道具が遠隔物体へ記録する手番 key を、対象物体ごとに集める。

    物体自身の interaction だけを見ていると、道具から書かれる key は読み込み
    時に導出できず、作者へ ``hidden_state_keys`` の重複宣言を要求してしまう。
    書き忘れが生の手番を漏らす形へ戻さないため、同じ効果宣言から導出する。
    """
    collected: dict[int, set[str]] = {}
    for item in items_raw:
        for interaction in item.get("interactions", ()) or ():
            for effect in interaction.get("effects", ()) or ():
                if effect.get("effect_type") != "RECORD_OBJECT_STATE_TICK":
                    continue
                parameters = effect.get("parameters", {}) or {}
                target = parameters.get("target_object")
                state_key = parameters.get("state_key")
                if not isinstance(target, str) or not isinstance(state_key, str):
                    continue
                object_id = mapper.get_int("object", target)
                collected.setdefault(object_id, set()).add(state_key)
    return {
        object_id: frozenset(keys)
        for object_id, keys in collected.items()
    }


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
    #: 世界の見取り図をシステムプロンプトに載せるか。
    #:
    #: **既定は載せない。** 初期は閉じている通路を持つシナリオが 11 本あり
    #: (abandoned_hospital は 16 部屋中 10 通路)、無条件に載せると鍵の向こうの
    #: 部屋が最初から見える。探索して見つける、という体験がその世界から消える。
    #:
    #: 秘匿役職ものでは逆に、全体の地図が無いとアリバイの検証ができない。
    #: 「集会室から物資庫は 2 tick かかる」を全員が知っていて初めて、時刻の
    #: 食い違いを突ける。世界によって要否が反転するので宣言にする。
    show_world_map: bool = False
    #: 役割キー → プロンプトに出す呼び名。
    #:
    #: ``crew`` / ``keeper`` は engine 側の識別子で、そのまま出すと #892 に
    #: 反する。**呼び名は世界ごとに違う** (クルー / 村人 / 乗員) ので
    #: シナリオが持つ。宣言の無い役割は人数だけ数えて名前を出さない。
    role_labels: Dict[str, str] = field(default_factory=dict)
    #: LLM の objective section に直接埋め込む「現在のゴール」テキスト。
    #: scenario の win condition を LLM 視点で書き下す (例: 「狼煙を上げて山頂で
    #: 救助される」「廃墟から外へ脱出する」)。空のときは world_runtime 等の
    #: consumer 側で fail-fast する (ハードコード fallback は意図的に置かない:
    #: シナリオごとに勝利条件が違うため、空のまま LLM を回すと別シナリオの
    #: objective が混入する silent failure になる)。
    llm_objective_text: str = ""
    #: 終局結果ごとの観測文型。世界固有の場所や語彙は runtime でなくここに置く。
    player_outcome_messages: Mapping[PlayerOutcomeEnum, str] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ItemSpecDefinition:
    """シナリオ JSON で定義されたアイテム仕様。"""
    string_id: str
    spec_id: ItemSpecId
    name: str
    description: str
    category: str
    is_light_source: bool = False
    # Phase D-2: 食料腐敗。None なら腐らない。値は正の整数 tick (loader でチェック)。
    spoils_after_ticks: Optional[int] = None
    # Phase F: 消費効果。None なら使えない (装備・素材など)。値があれば
    # runtime で ItemType.CONSUMABLE として登録される。複合効果は
    # CompositeItemEffect で表現。
    consume_effect: Optional["ItemEffect"] = None
    # PR β (実験 #29 後続): 疲労回復量。0 (default) なら効果なし。
    # use_item 成功時に PlayerStatusAggregate.recover_fatigue() が呼ばれる。
    fatigue_recovery: int = 0
    # Issue #794 D: item の一般用途。具体的な spot / object 名ではなく、
    # 「どういう用途で、どういう種類の場所が要るか」を作者が書く。
    usage_hint: str = ""


@dataclass(frozen=True)
class InitialItemSpec:
    """シナリオで「プレイヤーに最初から持たせるアイテム」を表す値オブジェクト。

    ItemSpecId に加えて per-instance state を仕込めるようにしたもの (Phase 4-D)。
    state を持たない単純な所持なら空 dict を渡せば、PR #115 までの挙動と同じ。
    state を入れた場合は ItemAggregate.create(state=...) 経由で初期 state を
    持つ instance が生成され、`ITEM_INSTANCE_STATE` precondition や
    reactive binding がそのまま機能する。
    """

    spec_id: ItemSpecId
    state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlayerSpawnConfig:
    """プレイヤー初期配置。

    `initial_state` は Phase 4-D-2 PR 3 で追加。`PlayerStatusAggregate.state`
    に渡せる JSON プリミティブの flat dict (str / int / float / bool / None)。
    シナリオ JSON で `players[].initial_state` を省略すれば空 dict になり、
    PR 1 までの挙動と同じ。
    """
    string_id: str
    player_id: int
    name: str
    spawn_spot_id: SpotId
    initial_items: Tuple[InitialItemSpec, ...]
    initial_state: Mapping[str, Any] = field(default_factory=dict)
    # Phase E: プレイヤー個別のペルソナ文 (system prompt に注入される)。
    # None なら runtime fallback (spawn 名から組み立てる generic persona)。
    # 各プレイヤーの「公開プロフィール + 秘密の動機 + 話し方」を 1 つの
    # text block にまとめて入れる想定。秘密はそのプレイヤーの prompt にしか
    # 入らないので natural な info asymmetry になる。
    persona_prompt: Optional[str] = None
    # 目的層 G6: このプレイヤー個別の初期目的文。goal store の seed に使われる。
    # None なら `metadata.llm_objective_text` (シナリオ共通) へフォールバックする
    # ので、既存シナリオの挙動は変わらない。persona_prompt と同じく、秘密の動機を
    # 含む目的をそのプレイヤーの prompt にだけ入れられる (= 情報の非対称性)。
    objective: Optional[str] = None
    # 目的層 G6: このプレイヤーの初期目的を改訂不可にするか。None なら従来どおり
    # シナリオ全体の性質 (`_scenario_has_goal`) から導出する。明示すればそれが
    # 優先され、「勝敗条件つきシナリオでもこの 1 人だけは立て直せる」が書ける。
    goal_locked: Optional[bool] = None
    # 経済統合 Phase 0: 所持金の初期値。省略すれば 0 で、宣言しないシナリオの
    # 挙動は変わらない。PlayerStatusAggregate への配線は売買ツールを入れる PR
    # の管轄なので、ここでは宣言の保持までを行う。
    initial_gold: int = 0


@dataclass(frozen=True)
class ScenarioWeatherConfig:
    """Spot Graph シナリオ用の軽量天候設定。"""

    enabled: bool
    initial_state: WeatherState
    update_interval_ticks: int
    announce_changes: bool


@dataclass(frozen=True)
class ScenarioDayNightConfig:
    """昼夜サイクル設定 (Phase B-1)。

    シナリオが昼夜の流れを必要としない (常に昼など) 場合は本 config を
    持たない (= ScenarioLoadResult.day_night_config が None)。
    """

    cycle: DayNightCycleDef
    # フェーズ変化時に同スポット内 player へ観測を流すか。サバイバル系
    # シナリオでは true (「夕暮れになった」「夜が明けた」)、パズル単発の
    # 短時間シナリオでは false でもよい。
    announce_changes: bool = True


@dataclass(frozen=True)
class AreaDef:
    """シナリオ JSON で宣言された area 定義。

    area は実行時 state を持たない軽い定義表で、spot のまとまりと遠景知覚の
    単位を表す。`position` は宣言値または所属 spot の重心で解決済み。

    `description` は **作者向けの覚書** で prompt には出さない
    (`metadata.description` と同じ扱い)。遠景に出す文は
    `distant_descriptions[距離帯]` → `visible_name` からの定型文の順で決まる
    (docs/spot_graph_distant_view_design.md)。エージェントに見せたい文を
    ここに書いても表示されない。読まれない理由が書いていなかったため、
    配線漏れと見分けが付かなくなっていた。

    `position_source` も同様に読まれない。`position` が宣言由来か重心算出かを
    記録する派生値で、作者が書くものではない。
    """

    area_id: str
    name: str
    visible_name: str
    prominence: float
    position: Optional[SpotPosition]
    position_source: Optional[str] = None
    description: str = ""
    distant_descriptions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DistantCueSourceDef:
    """遠景に出す動的兆候の発生条件。

    段階2aでは object_state のみ対応する。world_flag / scenario_flag は
    未対応の source.kind として loader 境界で fail-fast する。
    """

    kind: str
    object_id: SpotObjectId
    state_key: str
    equals: Any


@dataclass(frozen=True)
class DistantCueAppearEventDef:
    """動的兆候が false→true になった境界で配る観測の宣言。"""

    message: str
    schedules_turn: bool


@dataclass(frozen=True)
class DistantCueDef:
    """シナリオ JSON で宣言された汎用の遠望可能な兆候。

    signal_fire 固有の概念は持たせず、object state が条件を満たしたときに
    area 由来の遠景候補へ混ぜるための軽い定義表として扱う。
    """

    cue_id: str
    source: DistantCueSourceDef
    origin_area_id: str
    visible_name: str
    prominence: float
    ambient_descriptions: Mapping[str, str] = field(default_factory=dict)
    appear_event: Optional[DistantCueAppearEventDef] = None


@dataclass(frozen=True)
class ScenarioLootTableDefinition:
    """シナリオ JSON で宣言された LootTable 定義 (PR #1 動的 loot)。

    runtime で InMemoryLootTableRepository に詰め直すための薄いラッパ。
    string_id: シナリオ作家が JSON で参照する識別子 (例: "deep_fishing_loot")
    table_id: LootTableId として割り振った内部 id (mapper 経由)
    entries: (item_spec_id, weight, min_quantity, max_quantity) のタプル
    """
    string_id: str
    table_id: int
    name: str
    entries: Tuple["ScenarioLootEntry", ...]


@dataclass(frozen=True)
class ScenarioLootEntry:
    """LootTable の 1 エントリ。"""
    item_spec_id: int
    weight: int
    min_quantity: int = 1
    max_quantity: int = 1


@dataclass(frozen=True)
class ScenarioMerchantPriceEntry:
    """商人の品揃え 1 行 (「この item_spec をこの価格で売る / 買う」)。

    item_spec は読み込み時に int id へ解決済み。価格は 1 以上の整数で、
    無料や負の価格は宣言できない (loader が弾く)。
    """

    item_spec_id: int
    price: int


@dataclass(frozen=True)
class ScenarioMerchantDefinition:
    """シナリオ JSON で宣言された NPC 商人 (経済統合 Phase 0)。

    商人は spot に居る存在として宣言する。同席していないと売買できない、
    という「店の位置が意味を持つ」形にするため、spot 参照を必須にしている。

    string_id: シナリオ作家が JSON で参照する識別子 (例: "gustav")
    merchant_id: mapper の "merchant" 名前空間で割り振った内部 id
    name: 表示名。将来 LLM が商人を名前で指すため、シナリオ全域で一意
    sells: 商人が売る品と売値。空なら買い取り専門の商人
    buys: 商人が買い取る品と買値。空なら売るだけの商人

    同じ item_spec が sells と buys の両方に出るのは正常 (売値と買値の差が
    スプレッドになる)。禁じているのは片側リスト内での重複だけで、そちらは
    どちらの価格が効くか決まらないため。
    """

    string_id: str
    merchant_id: int
    name: str
    spot_id: SpotId
    sells: Tuple[ScenarioMerchantPriceEntry, ...] = ()
    buys: Tuple[ScenarioMerchantPriceEntry, ...] = ()


@dataclass(frozen=True)
class ScenarioNeedsConfig:
    """needs 機構のシナリオ別調整値。"""

    starvation_damage_per_tick: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.starvation_damage_per_tick, bool)
            or not isinstance(self.starvation_damage_per_tick, int)
            or self.starvation_damage_per_tick < 0
        ):
            raise ValueError(
                "starvation_damage_per_tick must be a non-negative integer, "
                f"got {self.starvation_damage_per_tick!r}"
            )


@dataclass(frozen=True)
class ScenarioMonsterTemplate:
    """シナリオ JSON で宣言されたモンスター種別定義 (Phase B-2a)。

    domain `MonsterTemplate` をそのまま保持する薄いラッパ + string_id (作家が
    JSON で参照するための識別子)。runtime で repository に詰める際に
    template_id (int) と string_id の対応も id_mapper に登録する。
    """

    string_id: str
    template: MonsterTemplate


@dataclass(frozen=True)
class ScenarioMonsterSpawnCondition:
    """モンスター出現を環境条件で制御する宣言 (Phase B-2b)。

    すべての軸が AND で合成される。指定が無い軸は常に成立扱い (= 「気にしない」)。
    値が一つでも指定されたら、その軸はマッチしないと spawn しない。

    Attributes:
        day_night_phase_names: 出現を許可する day_night フェーズの name 集合。
            空 tuple なら時間帯は問わない。シナリオ作家は自由命名できるので
            事前検証はせず、実行時に day_night cycle が宣言した phase との
            突合で一致 / 不一致だけ判定する。
        required_flags: ON 状態にあるべき WorldFlag。例: `["high_tide"]` で
            「満潮中のみ出現」を表現。空なら制約なし。
        forbidden_flags: OFF 状態にあるべき WorldFlag。例: `["high_tide"]` で
            「干潮中のみ出現」を表現。空なら制約なし。
        weather_type_names: 許容する WeatherTypeEnum 名 (例: ["STORM"])。
            空なら天候は問わない。
    """

    day_night_phase_names: Tuple[str, ...] = ()
    required_flags: Tuple[str, ...] = ()
    forbidden_flags: Tuple[str, ...] = ()
    weather_type_names: Tuple[str, ...] = ()

    @property
    def is_always(self) -> bool:
        """全軸が空なら「常に成立」(条件付きでない)。"""
        return (
            not self.day_night_phase_names
            and not self.required_flags
            and not self.forbidden_flags
            and not self.weather_type_names
        )


@dataclass(frozen=True)
class ScenarioMonsterPlacement:
    """モンスター個体の配置 (Phase B-2a で導入、B-2b で spawn_condition 拡張)。

    spawn_condition が None (省略) または `is_always == True` のとき:
      → シナリオ起動時に static 配置 (B-2a の挙動)
    spawn_condition がいずれかの軸で条件付きのとき:
      → SpotGraphMonsterSpawnService が tick 毎に条件評価し、満たすときだけ
        spawn (満たさなくなったら despawn) する動的 spawn (B-2b の挙動)

    同 spot に同 template を複数体並べる場合、各 placement が独立スロットになる
    (slot_key は `template@spot#index` を順序保存で生成する想定)。
    """

    template_string_id: str
    spot_string_id: str
    # 同じ spot に複数体置きたい時用に座標を分けられるよう保持。シナリオが省略
    # していれば (0, 0, 0)。spot-graph では座標は behavior の参照点として
    # 使われる程度。
    coordinate_x: int = 0
    coordinate_y: int = 0
    coordinate_z: int = 0
    # spawn_condition が None / is_always なら static 配置。それ以外は動的。
    spawn_condition: Optional[ScenarioMonsterSpawnCondition] = None


@dataclass(frozen=True)
class OngoingConditionDef:
    """進行中の世界フラグと、招集制限・明示的な解決効果。"""

    flag: str
    message: str
    blocks_emergency_button: bool
    resolution: Tuple[InteractionEffect, ...] = ()
    on_meeting_start: Tuple[InteractionEffect, ...] = ()


@dataclass(frozen=True)
class ScenarioLoadResult:
    graph: SpotGraphAggregate
    interiors: Dict[SpotId, SpotInterior]
    win_conditions: Tuple[GameEndCondition, ...]
    lose_conditions: Tuple[GameEndCondition, ...]
    player_spawns: Tuple[PlayerSpawnConfig, ...]
    item_spec_definitions: Tuple[ItemSpecDefinition, ...]
    item_interaction_registry: "ItemInteractionRegistry"
    id_mapper: ScenarioIdMapper
    metadata: ScenarioMetadata
    initial_flags: Tuple[str, ...]
    end_conditions: Tuple[GameEndCondition, ...] = ()
    scenario_events: Tuple[ScenarioEventDef, ...] = ()
    player_outcome_rules: Tuple[PlayerOutcomeRule, ...] = ()
    needs_config: ScenarioNeedsConfig = field(default_factory=ScenarioNeedsConfig)
    weather_config: Optional[ScenarioWeatherConfig] = None
    day_night_config: Optional[ScenarioDayNightConfig] = None
    reactive_passage_bindings: Tuple[ReactivePassageBinding, ...] = ()
    reactive_object_state_bindings: Tuple[ReactiveObjectStateBinding, ...] = ()
    synchronized_action_groups: Tuple[SynchronizedActionGroup, ...] = ()
    # 対人行為の定義。シナリオ直下に 1 回だけ書き、どこで使えるかは前提条件で
    # 表現する (spot object に紐づけると同じ行為の複数回定義が要るため)。
    player_interactions: Tuple[InteractionDef, ...] = ()
    monster_templates: Tuple[ScenarioMonsterTemplate, ...] = ()
    monster_placements: Tuple[ScenarioMonsterPlacement, ...] = ()
    # この世界では出さないツール。**世界の中身に無いものを出さないため**の宣言。
    #
    # モンスターの居ない世界に ``spot_graph_attack`` が並び続けるのが動機。
    # 対象候補が永久に空なのに毎ターン選択肢に載るので、実 run 007 では
    # インポスターが 3 手を捨てた。会議を宣言しない世界から投票系を落とす
    # のと同じ判断 (#860) だが、あちらは engine 側に条件を書いていた。
    # 何を出さないかは世界ごとに違うので、シナリオが決める。
    #
    # 名前は spot_graph 系ツールの実名で書く。記憶系ツールの露出は実験
    # profile の管轄なので、ここでは扱わない。
    disabled_tools: Tuple[str, ...] = ()
    # 同じ role の当事者同士だけが、互いを仲間として知る宣言。
    # role の生値は prompt へ渡さず、runtime が表示名へ解決する。
    mutually_known_roles: Tuple[str, ...] = ()
    # role ごとの不変な共通知識。個人の persona_prompt とは別に保持し、runtime が
    # 「人物 → 役職」の固定順で連結する。未宣言なら従来の persona_prompt だけを使う。
    role_personas: Mapping[str, str] = field(default_factory=dict)
    # 現在成立している異常を user prompt 末尾へ出す宣言。critical は後続の
    # 会議解除規則が読む分類であり、この段階では保持だけを行う。
    ongoing_conditions: Tuple[OngoingConditionDef, ...] = ()
    # PR #1 動的 loot: scenario JSON で宣言された LootTable 定義群。
    # runtime で InMemoryLootTableRepository に詰めて effect_service に注入する。
    loot_tables: Tuple[ScenarioLootTableDefinition, ...] = ()
    # 遠景知覚の土台: scenario JSON で宣言された area 定義群。
    # 実行時 state を持たないため、SpotGraphAggregate の子集約にはしない。
    areas: Tuple[AreaDef, ...] = ()
    # 遠景知覚の動的兆候: object state などを source とする定義群。
    # 段階2aでは読み込み・検証だけを行い、prompt 反映は段階2bで接続する。
    distant_cues: Tuple[DistantCueDef, ...] = ()
    # 会議機構を使うシナリオかどうか (会議と投票)。宣言の無いシナリオでは
    # 招集も投票も tool として出さず、runtime 側でも拒否する。
    #
    # 既定を False にしているのは、**比較実験の土台を黙って動かさない**ため。
    # #874 で report_body を無条件に出したとき、会議と無関係な
    # survival_island_v4_coop の tool 一覧が 16 → 17 に増え、過去 run との
    # 比較可能性が切れていた。同時行動 (prepare_action) と同じく、宣言した
    # シナリオにだけ出す。
    meeting_enabled: bool = False
    # 死の扱い。宣言が無ければ engine の既定 (蘇生できる世界)。
    death_semantics: DeathSemantics = field(default_factory=DeathSemantics)
    # 会議の調整値。None は既定 (GamePhaseStore のクラス定数) を使う。
    # シナリオごとに変えられないと、機構の確認用に短く回す run で会議 1 回
    # に run の大半を持っていかれる。
    meeting_tick_limit: Optional[int] = None
    meeting_silence_limit_ticks: Optional[int] = None
    meeting_cooldown_ticks: Optional[int] = None
    emergency_buttons_per_player: Optional[int] = None
    # DEAD 後も別位置で手番を持つ世界か。既定無効で比較実験を変えない。
    departed_agents_enabled: bool = False
    # 経済統合 Phase 2: エージェント同士の取引を使う世界か。
    #
    # 商人 (merchants) とは別の宣言にする。商人の居る町でも「人同士の取引は
    # しない」世界はありえるし、逆もある。meeting_enabled と同じく、宣言の
    # 無い世界では取引ツールを出さず、既存 run の tool 一覧を動かさない。
    player_trade_enabled: bool = False
    # 経済統合 Phase 0: この世界に居る NPC 商人の宣言。
    #
    # disabled_tools (負の宣言) と対になる**正の宣言**で、商人の居ない世界では
    # 空 tuple のままになる。売買ツールの露出判断はこの宣言を見る (PR-3)。
    # 既定を空 tuple にしているのは、既存シナリオを 1 つも書き換えずに
    # 過去 run との比較可能性を保つため。
    merchants: Tuple[ScenarioMerchantDefinition, ...] = ()


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
        if "outcome_resolution" in raw:
            raise ScenarioLoadError(
                "outcome_resolution は廃止されました。"
                "player_outcome_rules / game_end_conditions.end / needs を"
                "それぞれ宣言してください"
            )
        mapper = ScenarioIdMapper()

        metadata = self._parse_metadata(raw["metadata"])
        # item_specs 内の interaction も他の spot / object を参照できる。
        # ItemSpecDefinition の解析より前に全 ID を登録し、宣言順に依存しない。
        self._pre_register_ids(raw, mapper)
        item_defs = self._parse_item_specs(raw.get("item_specs", []), mapper)
        # PR #1: 動的 loot table を先にパース (effect parameter で
        # "loot_table" → id 解決するため、spots/effects のパース時点で
        # mapper に loot_table ns が登録済みである必要)。
        loot_tables = self._parse_loot_tables(raw.get("loot_tables", []), mapper)
        item_interaction_registry = self._parse_item_interaction_registry(
            raw.get("item_specs", []), mapper
        )
        graph, interiors = self._parse_spots_and_graph(
            raw,
            mapper,
            remote_recorded_tick_keys=_remote_recorded_tick_state_keys(
                raw.get("item_specs", []), mapper
            ),
        )
        areas = self._parse_areas(raw.get("areas", []), raw.get("spots", []))
        distant_cues = self._parse_distant_cues(
            raw.get("distant_cues", []),
            mapper,
            {area.area_id for area in areas},
        )
        self._parse_connections(raw.get("connections", []), graph, mapper)
        players = self._parse_players(raw.get("players", []), mapper)
        # 商人は spot と item_spec の両方を参照するので、どちらの登録も
        # 終わったこの時点で解析する。
        merchants = self._parse_merchants(raw.get("merchants"), mapper)
        mutually_known_roles = self._parse_mutually_known_roles(
            raw.get("mutually_known_roles"), players
        )
        role_personas = self._parse_role_personas(raw.get("role_personas"), players)
        raw_end_conditions = raw.get("game_end_conditions", {})
        win_conds = self._parse_end_conditions(
            raw_end_conditions.get("win", []), mapper, section="win"
        )
        lose_conds = self._parse_end_conditions(
            raw_end_conditions.get("lose", []), mapper, section="lose"
        )
        end_conds = self._parse_end_conditions(
            raw_end_conditions.get("end", []), mapper, section="end"
        )
        initial_flags = tuple(raw.get("initial_flags", []))
        ongoing_conditions = self._parse_ongoing_conditions(
            raw.get("ongoing_conditions"),
            declared_flag_writers=self._declared_world_flag_writers(raw),
            mapper=mapper,
        )
        self._validate_ongoing_condition_resolution_references(
            raw,
            ongoing_conditions,
        )
        disabled_tools = self._parse_disabled_tools(raw.get("disabled_tools"))
        scenario_events = self._parse_scenario_events(raw.get("scenario_events", []), mapper)
        player_outcome_rules = self._parse_player_outcome_rules(
            raw.get("player_outcome_rules", []), mapper,
        )
        needs_config = self._parse_needs_config(raw.get("needs"))
        weather_config = self._parse_weather_config(raw.get("environment", {}))
        day_night_config = self._parse_day_night_config(raw.get("environment", {}))
        monster_templates, monster_placements = self._parse_monsters_block(
            raw.get("monsters"), mapper,
        )
        reactive_bindings = self._parse_reactive_passage_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        reactive_object_bindings = self._parse_reactive_object_state_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        player_interactions = self._parse_player_interactions(
            raw.get("player_interactions", []), mapper,
        )
        sync_groups = self._parse_synchronized_action_groups(
            raw.get("synchronized_action_groups", []), mapper,
        )
        self._reject_unreachable_synchronized_action_names(sync_groups, raw)
        meeting_enabled = self._parse_meeting_enabled(raw)
        player_trade_enabled = self._parse_player_trade_enabled(raw)
        departed_agents_enabled = self._parse_departed_agents_enabled(raw)
        death_semantics = self._parse_death_semantics(raw)
        meeting_tuning = self._parse_meeting_tuning(raw)

        result = ScenarioLoadResult(
            graph=graph,
            interiors=interiors,
            win_conditions=tuple(win_conds),
            lose_conditions=tuple(lose_conds),
            player_spawns=tuple(players),
            item_spec_definitions=tuple(item_defs),
            item_interaction_registry=item_interaction_registry,
            id_mapper=mapper,
            metadata=metadata,
            initial_flags=initial_flags,
            end_conditions=tuple(end_conds),
            disabled_tools=disabled_tools,
            mutually_known_roles=mutually_known_roles,
            role_personas=role_personas,
            ongoing_conditions=ongoing_conditions,
            scenario_events=scenario_events,
            player_outcome_rules=player_outcome_rules,
            needs_config=needs_config,
            weather_config=weather_config,
            day_night_config=day_night_config,
            reactive_passage_bindings=reactive_bindings,
            reactive_object_state_bindings=reactive_object_bindings,
            synchronized_action_groups=sync_groups,
            player_interactions=player_interactions,
            monster_templates=monster_templates,
            monster_placements=monster_placements,
            loot_tables=loot_tables,
            areas=areas,
            distant_cues=distant_cues,
            meeting_enabled=meeting_enabled,
            death_semantics=death_semantics,
            departed_agents_enabled=departed_agents_enabled,
            merchants=merchants,
            player_trade_enabled=player_trade_enabled,
            **meeting_tuning,
        )
        self._validate_feature_consistency(result, raw)
        return result

    @staticmethod
    def _declared_world_flag_writers(raw: Mapping[str, Any]) -> frozenset[str]:
        """初期値と SET_FLAG から、このシナリオが成立させられる flag を集める。"""
        found: set[str] = set()
        initial_flags = raw.get("initial_flags")
        if isinstance(initial_flags, Mapping):
            found.update(
                key for key in initial_flags if isinstance(key, str) and key
            )
        elif isinstance(initial_flags, list):
            found.update(
                value for value in initial_flags if isinstance(value, str) and value
            )

        def visit(value: Any) -> None:
            if isinstance(value, Mapping):
                if value.get("effect_type") == "SET_FLAG":
                    parameters = value.get("parameters")
                    if isinstance(parameters, Mapping):
                        flag_name = parameters.get("flag_name")
                        if isinstance(flag_name, str) and flag_name:
                            found.add(flag_name)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        # ongoing_conditions 自身の on_meeting_start は、成立中の異常を解く側で
        # あって異常を発生させる側ではない。ここまで writer と数えると、同じ
        # 宣言内で初めて立つ循環 flag を「発生可能」と誤認してしまう。
        for key, value in raw.items():
            if key != "ongoing_conditions":
                visit(value)
        return frozenset(found)

    def _parse_ongoing_conditions(
        self,
        raw: Any,
        *,
        declared_flag_writers: frozenset[str],
        mapper: ScenarioIdMapper,
    ) -> Tuple[OngoingConditionDef, ...]:
        """異常表示を厳格に読み、永遠に成立しない flag 参照を拒否する。"""
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ScenarioLoadError("ongoing_conditions は配列で書いてください")

        allowed_keys = frozenset(
            {
                "flag",
                "message",
                "blocks_emergency_button",
                "resolution",
                "on_meeting_start",
            }
        )
        supported_resolution_effects = frozenset(
            {
                InteractionEffectTypeEnum.CLEAR_FLAG,
                InteractionEffectTypeEnum.SET_FLAG,
            }
        )
        supported_meeting_effects = frozenset(
            {
                InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION,
                InteractionEffectTypeEnum.SHOW_MESSAGE,
            }
        )
        parsed: list[OngoingConditionDef] = []
        seen_flags: set[str] = set()
        for index, entry in enumerate(raw):
            path = f"ongoing_conditions[{index}]"
            if not isinstance(entry, Mapping):
                raise ScenarioLoadError(f"{path} は object で書いてください")
            unknown_keys = set(entry) - allowed_keys
            if unknown_keys:
                raise ScenarioLoadError(
                    f"{path} に未知のキーがあります: {sorted(unknown_keys)}"
                )
            flag = entry.get("flag")
            if not isinstance(flag, str) or not flag.strip():
                raise ScenarioLoadError(f"{path}.flag は空でない文字列にしてください")
            flag = flag.strip()
            if flag in seen_flags:
                raise ScenarioLoadError(
                    f"ongoing_conditions に flag の重複があります: {flag}"
                )
            if flag not in declared_flag_writers:
                raise ScenarioLoadError(
                    f"{path}.flag={flag!r} は initial_flags にも SET_FLAG にも"
                    "宣言されていません"
                )
            message = entry.get("message")
            if not isinstance(message, str) or not message.strip():
                raise ScenarioLoadError(
                    f"{path}.message は空でない文字列にしてください"
                )
            blocks_emergency_button = entry.get("blocks_emergency_button")
            if not isinstance(blocks_emergency_button, bool):
                raise ScenarioLoadError(
                    f"{path}.blocks_emergency_button は true / false を"
                    "明示してください"
                )
            raw_resolution = entry.get("resolution", [])
            if not isinstance(raw_resolution, list):
                raise ScenarioLoadError(f"{path}.resolution は配列で書いてください")
            if "resolution" in entry and not raw_resolution:
                raise ScenarioLoadError(f"{path}.resolution は空にできません")
            resolution = tuple(
                self._parse_interaction_effect(
                    effect,
                    mapper,
                    actor_context="scenario_event",
                )
                for effect in raw_resolution
            )
            unsupported_resolution = [
                effect.effect_type.name
                for effect in resolution
                if effect.effect_type not in supported_resolution_effects
            ]
            if unsupported_resolution:
                raise ScenarioLoadError(
                    f"{path}.resolution にフラグ以外の効果があります: "
                    f"{unsupported_resolution}. 使える効果: CLEAR_FLAG, SET_FLAG"
                )
            if resolution and not any(
                effect.effect_type is InteractionEffectTypeEnum.CLEAR_FLAG
                and effect.parameters.get("flag_name") == flag
                for effect in resolution
            ):
                raise ScenarioLoadError(
                    f"{path}.resolution は成立条件の flag={flag!r} を"
                    "CLEAR_FLAG で解除してください"
                )
            raw_effects = entry.get("on_meeting_start", [])
            if not isinstance(raw_effects, list):
                raise ScenarioLoadError(
                    f"{path}.on_meeting_start は配列で書いてください"
                )
            if "on_meeting_start" in entry and not raw_effects:
                raise ScenarioLoadError(
                    f"{path}.on_meeting_start は空にできません。会議で解かない異常は"
                    "キー自体を省略してください"
                )
            effects = tuple(
                self._parse_interaction_effect(
                    effect,
                    mapper,
                    actor_context="scenario_event",
                )
                for effect in raw_effects
            )
            unsupported = [
                effect.effect_type.name
                for effect in effects
                if effect.effect_type not in supported_meeting_effects
            ]
            if unsupported:
                raise ScenarioLoadError(
                    f"{path}.on_meeting_start に未対応の効果があります: {unsupported}. "
                    "使える効果: RESOLVE_ONGOING_CONDITION, SHOW_MESSAGE"
                )
            if effects and not resolution:
                raise ScenarioLoadError(
                    f"{path}.on_meeting_start を使う異常には resolution が必要です"
                )
            if effects and not any(
                effect.effect_type
                is InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION
                and effect.parameters.get("flag") == flag
                for effect in effects
            ):
                raise ScenarioLoadError(
                    f"{path}.on_meeting_start は自身の flag={flag!r} を"
                    "RESOLVE_ONGOING_CONDITION で参照してください"
                )
            parsed.append(
                OngoingConditionDef(
                    flag=flag,
                    message=message.strip(),
                    blocks_emergency_button=blocks_emergency_button,
                    resolution=resolution,
                    on_meeting_start=effects,
                )
            )
            seen_flags.add(flag)
        return tuple(parsed)

    @staticmethod
    def _validate_ongoing_condition_resolution_references(
        raw: Mapping[str, Any],
        conditions: Sequence[OngoingConditionDef],
    ) -> None:
        """全 effect の異常解除参照が、実体のある resolution を指すと確かめる。"""
        resolvable = {
            condition.flag for condition in conditions if condition.resolution
        }

        def visit(value: Any, path: str) -> None:
            if isinstance(value, Mapping):
                if value.get("effect_type") == "RESOLVE_ONGOING_CONDITION":
                    parameters = value.get("parameters")
                    flag = parameters.get("flag") if isinstance(parameters, Mapping) else None
                    if not isinstance(flag, str) or not flag:
                        raise ScenarioLoadError(
                            f"{path} の RESOLVE_ONGOING_CONDITION は"
                            " parameters.flag を必要とします"
                        )
                    if flag not in resolvable:
                        raise ScenarioLoadError(
                            "RESOLVE_ONGOING_CONDITION が参照する flag に"
                            f" resolution がありません: flag={flag!r}, path={path}"
                        )
                for key, child in value.items():
                    visit(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{path}[{index}]")

        visit(raw, "scenario")

    @staticmethod
    def _parse_mutually_known_roles(
        raw: Any,
        players: Sequence[PlayerSpawnConfig],
    ) -> Tuple[str, ...]:
        """互いを知る role を読み、実在する複数人の集合だけを受理する。

        一人しかいない role は印を一つも生成せず、作者が開示したつもりのまま
        静かに効かない。少なくとも二人いることまで読み込み時に確かめる。
        """
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ScenarioLoadError("mutually_known_roles は配列で書いてください")
        roles: list[str] = []
        for value in raw:
            if not isinstance(value, str) or not value.strip():
                raise ScenarioLoadError(
                    "mutually_known_roles は空でない role 名の配列にしてください"
                )
            role = value.strip()
            if role in roles:
                raise ScenarioLoadError(
                    f"mutually_known_roles に重複があります: {role}"
                )
            count = sum(
                1 for player in players if player.initial_state.get("role") == role
            )
            if count < 2:
                raise ScenarioLoadError(
                    f"mutually_known_roles の {role} には二人以上必要です: {count}人"
                )
            roles.append(role)
        return tuple(roles)

    @staticmethod
    def _parse_role_personas(
        raw: Any,
        players: Sequence[PlayerSpawnConfig],
    ) -> Mapping[str, str]:
        """役職共通文を検証し、宣言順を保った mapping として返す。"""
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ScenarioLoadError("role_personas は role 名から文章への object で書いてください")

        declared_roles = {
            role
            for player in players
            if isinstance((role := player.initial_state.get("role")), str) and role
        }
        parsed: Dict[str, str] = {}
        for role, persona in raw.items():
            if not isinstance(role, str) or not role.strip():
                raise ScenarioLoadError("role_personas のキーは空でない role 名にしてください")
            normalized_role = role.strip()
            if normalized_role in parsed:
                raise ScenarioLoadError(
                    f"role_personas に正規化後の重複があります: {normalized_role}"
                )
            if normalized_role not in declared_roles:
                raise ScenarioLoadError(
                    f"role_personas に player が一人も持たない role があります: {normalized_role}"
                )
            if not isinstance(persona, str) or not persona.strip():
                raise ScenarioLoadError(
                    f"role_personas.{normalized_role} は空でない文字列にしてください"
                )
            parsed[normalized_role] = persona.strip()
        return parsed

    @staticmethod
    def _validate_feature_consistency(
        scenario: ScenarioLoadResult,
        raw: Mapping[str, Any],
    ) -> None:
        """個別には正しい宣言が、機能の組合せとして成立するか検査する。"""
        classified_conditions = set(_INTERACTION_CONDITION_FEATURE_REQUIREMENTS)
        known_conditions = set(InteractionConditionTypeEnum)
        if classified_conditions != known_conditions:
            raise ScenarioLoadError(
                "環境機能への依存が未分類の interaction condition があります: "
                f"未分類={sorted(c.value for c in known_conditions - classified_conditions)}, "
                f"廃止済み={sorted(c.value for c in classified_conditions - known_conditions)}"
            )

        exposure = ToolExposure.from_scenario(
            scenario,
            meeting_declared=scenario.meeting_enabled,
        )
        if (
            scenario.death_semantics.grace_ticks == 0
            and exposure.is_exposed("tend_to_player")
        ):
            raise ScenarioLoadError(
                "death.grace_ticks が 0 の世界では tend_to_player を "
                "disabled_tools に指定してください"
            )

        nodes = tuple(ScenarioLoader._iter_mappings(raw))
        if any(
            node.get("effect_type") == InteractionEffectTypeEnum.CALL_MEETING.value
            for node in nodes
        ):
            if not scenario.meeting_enabled:
                raise ScenarioLoadError(
                    "CALL_MEETING を使うシナリオには有効な meeting 宣言が必要です"
                )

        day_night_condition_names = {
            condition.value
            for condition, feature in _INTERACTION_CONDITION_FEATURE_REQUIREMENTS.items()
            if feature == _DAY_NIGHT_FEATURE
        }
        uses_day_night = any(
            node.get("condition_type") in day_night_condition_names
            or any(
                bool(node.get(key))
                for key, feature in _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS.items()
                if feature == _DAY_NIGHT_FEATURE
            )
            for node in nodes
        )
        if uses_day_night and scenario.day_night_config is None:
            raise ScenarioLoadError(
                "時間帯条件を使うシナリオには有効な environment.day_night が必要です"
            )

        # 条件が指すフェーズ名が、そのシナリオが宣言したフェーズに実在すること。
        #
        # 素通りさせると 2 つが同時に起きる。条件は永久に不成立になり (作者は
        # 「まだその時刻になっていない」と読む)、ヒントには `"predawnのみ"` と
        # **内部識別子がプロンプトへ出る**。
        #
        # `required_lighting` は既に enum 検証を持っていたのに、時刻帯と天候だけ
        # 素通りしていた。時刻帯は enum ではなく**シナリオ自由命名**なので、
        # 照合相手は enum ではなくそのシナリオの宣言になる。
        declared_phases = {
            phase.name
            for phase in (
                scenario.day_night_config.cycle.phases
                if scenario.day_night_config is not None
                else ()
            )
        }
        if declared_phases:
            unknown = sorted(
                {
                    str(node["required_time_of_day_phase"])
                    for node in nodes
                    if node.get("required_time_of_day_phase")
                }
                - declared_phases
            )
            if unknown:
                raise ScenarioLoadError(
                    f"required_time_of_day_phase に、宣言されていないフェーズ名が"
                    f" あります: {unknown}。"
                    f" environment.day_night.phases で宣言した名前"
                    f" {sorted(declared_phases)} のいずれかを書いてください。"
                )

        weather_condition_names = {
            condition.value
            for condition, feature in _INTERACTION_CONDITION_FEATURE_REQUIREMENTS.items()
            if feature == _WEATHER_FEATURE
        }
        uses_weather = any(
            node.get("condition_type") in weather_condition_names
            or any(
                bool(node.get(key))
                for key, feature in _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS.items()
                if feature == _WEATHER_FEATURE
            )
            for node in nodes
        )
        if uses_weather and (
            scenario.weather_config is None or not scenario.weather_config.enabled
        ):
            raise ScenarioLoadError(
                "天候条件を使うシナリオには有効な environment.weather が必要です"
            )

    @staticmethod
    def _iter_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
        """JSON内の全objectを、配置を手動列挙せず再帰的に返す。"""
        if isinstance(value, Mapping):
            yield value
            for child in value.values():
                yield from ScenarioLoader._iter_mappings(child)
        elif isinstance(value, list):
            for child in value:
                yield from ScenarioLoader._iter_mappings(child)

    @staticmethod
    def _parse_meeting_tuning(raw: Dict[str, Any]) -> Dict[str, Optional[int]]:
        """`meeting` block の調整値を読む。書かれていない項目は None (既定)。

        **1 以上の整数だけを通す。** 0 や負を許すと、会議が始まった瞬間に
        打ち切られたり、クールダウンが効かなくなったりする。読み込み時に
        止めないと、run が終わるまで「なぜか会議が成立しない」で悩む。
        """
        block = raw.get("meeting")
        keys = (
            "tick_limit",
            "silence_limit_ticks",
            "cooldown_ticks",
            "emergency_buttons_per_player",
        )
        if not isinstance(block, dict):
            return {f"meeting_{k}": None for k in keys[:3]} | {
                "emergency_buttons_per_player": None
            }
        parsed: Dict[str, Optional[int]] = {}
        for key in keys:
            value = block.get(key)
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ScenarioLoadError(
                        f"meeting.{key} は整数で指定してください"
                    )
                if value < 1:
                    raise ScenarioLoadError(
                        f"meeting.{key} は 1 以上である必要があります: {value}"
                    )
            field = (
                key
                if key == "emergency_buttons_per_player"
                else f"meeting_{key}"
            )
            parsed[field] = value
        return parsed

    @staticmethod
    def _parse_death_semantics(raw: Dict[str, Any]) -> DeathSemantics:
        """`death` block を読む。書かれていない項目は engine の既定。

        `grace_ticks` は 0 を許す (即死の世界)。負は拒否する。0 と「書き
        忘れ」を区別するため、既定は None で持つ。
        """
        block = raw.get("death")
        if block is None:
            return DeathSemantics()
        if not isinstance(block, dict):
            raise ScenarioLoadError("death は object で指定してください。")
        grace = block.get("grace_ticks")
        if grace is not None:
            if not isinstance(grace, int) or isinstance(grace, bool) or grace < 0:
                raise ScenarioLoadError(
                    f"death.grace_ticks は 0 以上の整数で指定してください: {grace!r}"
                )
        for key in ("announce_globally", "victim_learns_killer"):
            if key in block and not isinstance(block[key], bool):
                raise ScenarioLoadError(f"death.{key} は真偽値で指定してください。")
        return DeathSemantics(
            grace_ticks=grace,
            announce_globally=block.get("announce_globally", True),
            victim_learns_killer=block.get("victim_learns_killer", True),
        )

    @staticmethod
    def _parse_player_trade_enabled(raw: Dict[str, Any]) -> bool:
        """`player_trade` block からエージェント同士の取引の on/off を決める。

        block が無ければ off。書いたなら既定は on とする (書いておいて既定
        off だと、宣言したのに何も起きない静かな失敗になる)。`meeting` と
        同じ流儀。
        """
        block = raw.get("player_trade")
        if block is None:
            return False
        if not isinstance(block, dict):
            raise ScenarioLoadError(
                "player_trade は object で指定してください。"
            )
        enabled = block.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ScenarioLoadError(
                "player_trade.enabled は真偽値で指定してください。"
            )
        return enabled

    @staticmethod
    def _parse_meeting_enabled(raw: Dict[str, Any]) -> bool:
        """`meeting` block の有無と `enabled` から会議機構の on/off を決める。

        block そのものが無ければ off。block を書いたなら既定は on とする
        (書いておいて既定 off だと、宣言したのに何も起きない静かな失敗になる)。
        明示的に `"enabled": false` と書いた場合だけ off に落とす。
        """
        block = raw.get("meeting")
        if block is None:
            return False
        if not isinstance(block, dict):
            raise ScenarioLoadError(
                "meeting は object で指定してください。"
            )
        enabled = block.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ScenarioLoadError(
                "meeting.enabled は真偽値で指定してください。"
            )
        return enabled

    def _parse_loot_tables(
        self,
        raw_list: List[Dict[str, Any]],
        mapper: ScenarioIdMapper,
    ) -> Tuple[ScenarioLootTableDefinition, ...]:
        """`loot_tables` block を解析する (PR #1 動的 loot)。

        スキーマ:
          "loot_tables": [
            {
              "id": "deep_fishing_loot",
              "name": "沖の釣り" (optional),
              "entries": [
                {"item_spec": "raw_fish", "weight": 70, "min_quantity": 1, "max_quantity": 2},
                {"item_spec": "shellfish", "weight": 20},
                {"item_spec": "treasure_compass", "weight": 1}
              ]
            }
          ]

        IDs は mapper に "loot_table" 名前空間で登録する。
        """
        out: List[ScenarioLootTableDefinition] = []
        for raw in raw_list:
            string_id = raw.get("id")
            if not isinstance(string_id, str) or not string_id:
                raise ScenarioLoadError(
                    f"loot_tables[*].id is required (got {string_id!r})"
                )
            table_id = mapper.register("loot_table", string_id)
            entries_raw = raw.get("entries", [])
            if not entries_raw:
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries must be non-empty"
                )
            entries: List[ScenarioLootEntry] = []
            for index, e in enumerate(entries_raw):
                item_sid = e.get("item_spec")
                if not isinstance(item_sid, str):
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].item_spec required"
                    )
                # PR #1 follow-up: 数値変換失敗 (例: weight="abc") は Python の
                # ValueError として落ちると場所が分からない。シナリオ作家が
                # 直すべき項目を ScenarioLoadError に包んで surface する。
                try:
                    weight = int(e.get("weight", 1))
                    min_q = int(e.get("min_quantity", 1))
                    max_q = int(e.get("max_quantity", 1))
                except (TypeError, ValueError) as exc:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}] has "
                        f"non-integer weight/quantity: {e!r}"
                    ) from exc
                if weight < 0:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].weight "
                        f"must be >= 0 (got {weight})"
                    )
                if min_q < 1:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].min_quantity "
                        f"must be >= 1 (got {min_q})"
                    )
                if max_q < min_q:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].max_quantity "
                        f"({max_q}) must be >= min_quantity ({min_q})"
                    )
                entries.append(ScenarioLootEntry(
                    item_spec_id=mapper.get_int("item_spec", item_sid),
                    weight=weight,
                    min_quantity=min_q,
                    max_quantity=max_q,
                ))
            out.append(ScenarioLootTableDefinition(
                string_id=string_id,
                table_id=table_id,
                name=raw.get("name", ""),
                entries=tuple(entries),
            ))
        return tuple(out)

    def _parse_merchants(
        self,
        raw_block: Any,
        mapper: ScenarioIdMapper,
    ) -> Tuple[ScenarioMerchantDefinition, ...]:
        """`merchants` block を解析する (経済統合 Phase 0)。

        スキーマ:
          "merchants": [
            {
              "id": "gustav",
              "name": "商人グスタフ",
              "spot": "market_square",
              "sells": [{"item_spec": "bread", "price": 10}],
              "buys": [{"item_spec": "herb", "price": 6}]
            }
          ]

        未宣言・空配列はどちらも空 tuple (商人の居ない世界) として扱う。
        参照 (spot / item_spec) はこの時点で解決し、実在しない名前は
        実行前に落とす。
        """
        if raw_block is None:
            return ()
        if not isinstance(raw_block, list):
            raise ScenarioLoadError(
                f"merchants は配列で宣言してください (got {type(raw_block).__name__})"
            )

        merchants: List[ScenarioMerchantDefinition] = []
        seen_ids: set = set()
        seen_names: set = set()
        for index, raw in enumerate(raw_block):
            if not isinstance(raw, dict):
                raise ScenarioLoadError(
                    f"merchants[{index}] はオブジェクトで宣言してください "
                    f"(got {type(raw).__name__})"
                )
            string_id = self._parse_merchant_id(raw.get("id"), index=index)
            if string_id in seen_ids:
                raise ScenarioLoadError(
                    f"merchants[{index}].id が重複しています: {string_id!r}"
                )
            seen_ids.add(string_id)

            name = self._parse_merchant_name(raw.get("name"), string_id=string_id)
            if name in seen_names:
                # 名前が重なると、将来 LLM が名前で商人を指すときに
                # どちらの商人か決まらない。宣言の時点で潰す。
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].name がほかの商人と重複しています: {name!r}"
                )
            seen_names.add(name)

            spot_id = self._parse_merchant_spot(
                raw.get("spot"), mapper, string_id=string_id,
            )
            sells = self._parse_merchant_price_list(
                raw.get("sells"), mapper, string_id=string_id, section="sells",
            )
            buys = self._parse_merchant_price_list(
                raw.get("buys"), mapper, string_id=string_id, section="buys",
            )
            if not sells and not buys:
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}] は sells と buys が両方空です。"
                    "売る品か買い取る品のどちらかを宣言してください"
                )

            merchants.append(ScenarioMerchantDefinition(
                string_id=string_id,
                merchant_id=mapper.register("merchant", string_id),
                name=name,
                spot_id=spot_id,
                sells=sells,
                buys=buys,
            ))
        return tuple(merchants)

    @staticmethod
    def _parse_merchant_id(raw: Any, *, index: int) -> str:
        """`merchants[].id` を検証する。"""
        if not isinstance(raw, str) or not raw:
            raise ScenarioLoadError(
                f"merchants[{index}].id は空でない文字列で宣言してください (got {raw!r})"
            )
        return raw

    @staticmethod
    def _parse_merchant_name(raw: Any, *, string_id: str) -> str:
        """`merchants[].name` を検証する (表示名なので空白のみも弾く)。"""
        if not isinstance(raw, str) or not raw.strip():
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].name は空でない文字列で宣言してください "
                f"(got {raw!r})"
            )
        return raw.strip()

    @staticmethod
    def _parse_merchant_spot(
        raw: Any, mapper: ScenarioIdMapper, *, string_id: str,
    ) -> SpotId:
        """`merchants[].spot` を検証し、実在する spot への参照へ解決する。"""
        if not isinstance(raw, str) or not raw:
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].spot は空でない文字列で宣言してください "
                f"(got {raw!r})"
            )
        if not mapper.contains("spot", raw):
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].spot が実在しない spot を参照しています: {raw!r}"
            )
        return SpotId.create(mapper.get_int("spot", raw))

    def _parse_merchant_price_list(
        self,
        raw_list: Any,
        mapper: ScenarioIdMapper,
        *,
        string_id: str,
        section: str,
    ) -> Tuple[ScenarioMerchantPriceEntry, ...]:
        """`merchants[].sells` / `.buys` を解析する。

        同じ item_spec を同一リスト内に 2 度書くのは、どちらの価格が効くか
        決まらないので弾く。sells と buys にまたがる重複はスプレッドの土台
        なので許す。
        """
        if raw_list is None:
            return ()
        if not isinstance(raw_list, list):
            raise ScenarioLoadError(
                f"merchants[{string_id!r}].{section} は配列で宣言してください "
                f"(got {type(raw_list).__name__})"
            )

        entries: List[ScenarioMerchantPriceEntry] = []
        seen_item_specs: set = set()
        for index, raw in enumerate(raw_list):
            if not isinstance(raw, dict):
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].{section}[{index}] はオブジェクトで"
                    f"宣言してください (got {type(raw).__name__})"
                )
            item_spec = raw.get("item_spec")
            if not isinstance(item_spec, str) or not item_spec:
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].{section}[{index}].item_spec は"
                    f"空でない文字列で宣言してください (got {item_spec!r})"
                )
            if not mapper.contains("item_spec", item_spec):
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].{section}[{index}].item_spec が"
                    f"実在しない item_spec を参照しています: {item_spec!r}"
                )
            if item_spec in seen_item_specs:
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].{section} に同じ item_spec が"
                    f"二度宣言されています: {item_spec!r}"
                )
            seen_item_specs.add(item_spec)

            price = raw.get("price")
            # bool を除くのは、True が int として通ると price=1 の宣言と
            # 見分けが付かなくなるため。
            if isinstance(price, bool) or not isinstance(price, int):
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].{section}[{index}].price は"
                    f"整数で宣言してください (got {price!r})"
                )
            if price <= 0:
                raise ScenarioLoadError(
                    f"merchants[{string_id!r}].{section}[{index}].price は"
                    f"1 以上で宣言してください (got {price})"
                )
            entries.append(ScenarioMerchantPriceEntry(
                item_spec_id=mapper.get_int("item_spec", item_spec),
                price=price,
            ))
        return tuple(entries)

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
            show_world_map=_parse_show_world_map(raw),
            role_labels=_parse_role_labels(raw),
            llm_objective_text=str(raw.get("llm_objective_text", "") or "").strip(),
            player_outcome_messages=_parse_player_outcome_messages(raw),
        )

    def _pre_register_ids(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> None:
        """スポット・接続・オブジェクトの全 ID を先行登録する。

        interaction effect が他スポットの接続やオブジェクトを参照する場合に備え、
        実体の解析よりも先に全名前空間の ID を確定させる。
        """
        for spot in raw.get("spots", []):
            mapper.register("spot", spot["id"])
            interior = spot.get("interior", {})
            seen_object_ids: set = set()
            for obj in interior.get("objects", []):
                object_id = obj["id"]
                # **同じ spot に同じ id の object を 2 つ書くのを止める。**
                # 黙って通すと、後から書いたほうの interaction が実行時に
                # 「そんな操作は無い」で落ちる。JSON には確かに書いてあるので、
                # 原因にたどり着くまでが長い (実際にこれで詰まった)。
                if object_id in seen_object_ids:
                    raise ScenarioLoadError(
                        f"spot '{spot['id']}' に object id '{object_id}' が"
                        "重複しています。後から書いたほうの interaction は"
                        "実行時に見つからなくなります"
                    )
                seen_object_ids.add(object_id)
                mapper.register("object", object_id)
            for sub in interior.get("sub_locations", []):
                mapper.register("sub_location", sub["id"])
        for conn in raw.get("connections", []):
            mapper.register("connection", conn["id"])
            if _parse_bool(
                conn.get("is_bidirectional", True),
                path=f"connection {conn.get('id')}.is_bidirectional",
            ):
                mapper.register("connection", conn["id"] + "__reverse")
        for player in raw.get("players", []):
            mapper.register("player", player["id"])
        for item in raw.get("item_specs", []):
            mapper.register("item_spec", item["id"])

    def _parse_item_interaction_registry(
        self,
        items_raw: List[Dict[str, Any]],
        mapper: ScenarioIdMapper,
    ) -> "ItemInteractionRegistry":
        """item_specs の操作を world_graph 側の登録簿へ射影する。

        次の効果は物体 interaction では対象省略時に操作元の物体へ作用する。
        道具 interaction にはその物体が無いため、``target_object`` の明示を
        必須にする: ``DEPOSIT_ITEM_TO_OBJECT``, ``INCREMENT_OBJECT_STATE``,
        ``CONSUME_OBJECT_STOCK``, ``CHANGE_OBJECT_STATE``,
        ``RECORD_OBJECT_STATE_TICK``, ``WRITE_PLAYER_TEXT``,
        ``SHOW_PLAYER_TEXT``。省略を黙って無効化すると、作者の宣言だけが残る
        静かな失敗になるため読み込み時に止める。

        道具の待ち時間キーは ``(ItemSpecId, cooldown_key)`` で、共有単位は
        ``cooldown_scope`` が actor / world のどちらかを決める。group 未指定なら
        action_name ごとに独立し、同じ group を明示した操作だけが待ち時間を共有する。
        ItemSpecId を含めるので、別品目の同名 group は衝突しない。
        """
        from ai_rpg_world.domain.world_graph.service.item_interaction_registry import (
            ItemInteractionRegistry,
        )

        implicit_object_effects = frozenset(
            {
                InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
                InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE,
                InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK,
                InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
                InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
                InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
            }
        )
        entries: Dict[ItemSpecId, Tuple[InteractionDef, ...]] = {}
        for item in items_raw:
            interactions = tuple(
                self._parse_interaction_def(raw, mapper)
                for raw in item.get("interactions", [])
            )
            action_names = [interaction.action_name for interaction in interactions]
            if len(set(action_names)) != len(action_names):
                duplicated = next(
                    name for name in action_names if action_names.count(name) > 1
                )
                raise ScenarioLoadError(
                    f"item '{item['id']}' interaction action_name "
                    f"'{duplicated}' が重複しています"
                )
            for interaction in interactions:
                for effect in interaction.effects:
                    if (
                        effect.effect_type in implicit_object_effects
                        and "object_id" not in effect.parameters
                    ):
                        raise ScenarioLoadError(
                            f"item '{item['id']}' interaction "
                            f"'{interaction.action_name}': {effect.effect_type.value} "
                            "requires parameters.target_object"
                        )
            if interactions:
                entries[ItemSpecId.create(mapper.get_int("item_spec", item["id"]))] = (
                    interactions
                )
        return ItemInteractionRegistry(entries)

    def _parse_consume_effect(
        self, raw: Any, sid: str,
    ) -> Optional[ItemEffect]:
        """JSON の consume_effect (単一 dict or list) を ItemEffect に変換する。

        対応形式:
        - None / 未指定 → None (使えないアイテム)
        - 単一 dict: `{"type": "heal_hp", "amount": 5}`
        - list: `[{"type": "heal_hp", "amount": 5}, {"type": "satisfy_need", ...}]`
          → CompositeItemEffect でまとめる (1 要素なら単一として返す)
        """
        if raw is None:
            return None
        # 統一して list に正規化
        entries = raw if isinstance(raw, list) else [raw]
        if not entries:
            return None
        parsed = [self._parse_single_consume_effect(e, sid) for e in entries]
        if len(parsed) == 1:
            return parsed[0]
        return CompositeItemEffect(effects=tuple(parsed))

    def _parse_single_consume_effect(
        self, entry: Dict[str, Any], sid: str,
    ) -> ItemEffect:
        """1 つの effect dict を ItemEffect サブクラスに変換する。"""
        if not isinstance(entry, dict):
            raise ValueError(
                f"item '{sid}': consume_effect entry must be a dict, got {type(entry).__name__}"
            )
        etype = entry.get("type")
        if not etype:
            raise ValueError(f"item '{sid}': consume_effect entry missing 'type'")
        if etype == "heal_hp":
            return HealEffect(amount=int(entry["amount"]))
        if etype == "damage_hp":
            return DamageHpEffect(amount=int(entry["amount"]))
        if etype == "recover_mp":
            return RecoverMpEffect(amount=int(entry["amount"]))
        if etype == "gold":
            return GoldEffect(amount=int(entry["amount"]))
        if etype == "exp":
            return ExpEffect(amount=int(entry["amount"]))
        if etype == "satisfy_need":
            need = entry.get("need_type") or entry.get("need_type_name")
            if not need:
                raise ValueError(
                    f"item '{sid}': satisfy_need requires 'need_type' (e.g. 'HUNGER')"
                )
            return SatisfyNeedEffect(
                need_type_name=str(need), amount=int(entry["amount"]),
            )
        if etype == "revive":
            # Issue #621 Phase 3a: ダウン player を蘇生する効果。
            # hp_rate は max_hp に対する比率 (0.0-1.0)。範囲 validation は
            # ReviveEffect.__post_init__ が ItemEffectValidationException で行う。
            if "hp_rate" not in entry:
                raise ValueError(
                    f"item '{sid}': revive requires 'hp_rate' (e.g. 0.4)"
                )
            return ReviveEffect(hp_rate=float(entry["hp_rate"]))
        raise ValueError(
            f"item '{sid}': unknown consume_effect type '{etype}' "
            "(expected: heal_hp / damage_hp / recover_mp / gold / exp / satisfy_need / revive)"
        )

    def _parse_item_specs(
        self, items_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> List[ItemSpecDefinition]:
        defs: List[ItemSpecDefinition] = []
        for item in items_raw:
            sid = item["id"]
            numeric = mapper.register("item_spec", sid)
            spoils_raw = item.get("spoils_after_ticks")
            spoils_after_ticks: Optional[int] = None
            if spoils_raw is not None:
                # 不正値はシナリオ作家ミスとして boundary で弾く。ItemSpec の
                # __post_init__ でも弾かれるが、ここで明示しておくと loader 段で
                # 早期 fail し、エラー位置が JSON 単位で分かりやすい。
                spoils_after_ticks = int(spoils_raw)
                if spoils_after_ticks <= 0:
                    raise ValueError(
                        f"item '{sid}': spoils_after_ticks must be positive, got {spoils_after_ticks}"
                    )
            consume_effect = self._parse_consume_effect(
                item.get("consume_effect"), sid,
            )
            fatigue_recovery_raw = item.get("fatigue_recovery", 0)
            try:
                fatigue_recovery = int(fatigue_recovery_raw)
            except (TypeError, ValueError):
                raise ValueError(
                    f"item '{sid}': fatigue_recovery must be int, got {fatigue_recovery_raw!r}"
                )
            if fatigue_recovery < 0:
                raise ValueError(
                    f"item '{sid}': fatigue_recovery must be non-negative, got {fatigue_recovery}"
                )
            usage_hint_raw = item.get("usage_hint", "")
            if not isinstance(usage_hint_raw, str):
                raise ValueError(
                    f"item '{sid}': usage_hint must be string, got {usage_hint_raw!r}"
                )
            usage_hint = usage_hint_raw.strip()
            if "usage_hint" in item and not usage_hint:
                raise ValueError(f"item '{sid}': usage_hint must not be blank")
            defs.append(ItemSpecDefinition(
                string_id=sid,
                spec_id=ItemSpecId.create(numeric),
                name=item["name"],
                description=item.get("description", ""),
                category=item.get("category", "GENERAL"),
                is_light_source=_parse_bool(
                    item.get("is_light_source", False),
                    path=f"item {sid}.is_light_source",
                ),
                spoils_after_ticks=spoils_after_ticks,
                consume_effect=consume_effect,
                fatigue_recovery=fatigue_recovery,
                usage_hint=usage_hint,
            ))
        return defs

    def _parse_spots_and_graph(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        remote_recorded_tick_keys: Mapping[int, frozenset[str]],
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
            position = self._parse_spot_position(sid_str, spot_raw.get("position"))
            area_id = self._parse_spot_area_id(sid_str, spot_raw.get("area_id"))

            node = SpotNode(
                spot_id=spot_id,
                name=spot_raw["name"],
                description=spot_raw["description"],
                category=category,
                parent_id=parent_id,
                interior=None,
                atmosphere=atmosphere,
                is_outdoor=_parse_bool(
                    spot_raw.get("is_outdoor", False),
                    path=f"spot {sid_str}.is_outdoor",
                ),
                position=position,
                area_id=area_id,
            )
            graph.add_spot(node)

            interior_raw = spot_raw.get("interior")
            if interior_raw:
                interiors[spot_id] = self._parse_interior(
                    interior_raw,
                    mapper,
                    remote_recorded_tick_keys=remote_recorded_tick_keys,
                )
            else:
                interiors[spot_id] = SpotInterior.empty()

        graph.clear_events()
        return graph, interiors

    def _parse_spot_position(self, spot_id: str, raw: Any) -> Optional[SpotPosition]:
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
        x = self._parse_position_number(raw.get("x"), f"{path}.x")
        y = self._parse_position_number(raw.get("y"), f"{path}.y")
        return SpotPosition(x=x, y=y)

    def _parse_position_number(self, raw: Any, path: str) -> float:
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ScenarioLoadError(f"{path} must be a number")
        value = float(raw)
        if not isfinite(value):
            raise ScenarioLoadError(f"{path} must be a finite number")
        return value

    def _parse_spot_area_id(self, spot_id: str, raw: Any) -> Optional[str]:
        if raw is None:
            return None
        if not isinstance(raw, str) or not raw.strip():
            raise ScenarioLoadError(f"spots[{spot_id}].area_id must be a non-empty string")
        return raw.strip()

    def _parse_areas(
        self,
        areas_raw: Any,
        spots_raw: Any,
    ) -> Tuple[AreaDef, ...]:
        if areas_raw is None:
            return ()
        if not isinstance(areas_raw, Sequence) or isinstance(areas_raw, (str, bytes)):
            raise ScenarioLoadError("areas must be a list")

        spot_positions_by_area = self._spot_positions_by_area(spots_raw)
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
            prominence = self._parse_prominence(
                raw_area.get("prominence"), f"areas[{area_id}].prominence"
            )

            declared_position = self._parse_area_position(area_id, raw_area.get("position"))
            if declared_position is not None:
                position = declared_position
                position_source = "declared"
            else:
                position = self._area_centroid(spot_positions_by_area.get(area_id, ()))
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

    def _parse_area_position(self, area_id: str, raw: Any) -> Optional[SpotPosition]:
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
        x = self._parse_position_number(raw.get("x"), f"{path}.x")
        y = self._parse_position_number(raw.get("y"), f"{path}.y")
        return SpotPosition(x=x, y=y)

    def _parse_prominence(self, raw: Any, path: str) -> float:
        value = self._parse_position_number(raw, path)
        if not 0.0 <= value <= 1.0:
            raise ScenarioLoadError(f"{path} must be in [0.0, 1.0]")
        return value

    def _parse_distant_cues(
        self,
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

            source = self._parse_distant_cue_source(cue_id, raw_cue.get("source"), mapper)
            origin_area_id = self._parse_distant_cue_origin_area_id(
                cue_id, raw_cue.get("origin"), area_ids
            )

            visible_name = raw_cue.get("visible_name")
            if not isinstance(visible_name, str) or not visible_name.strip():
                raise ScenarioLoadError(
                    f"distant_cues[{cue_id}].visible_name must be a non-empty string"
                )
            prominence = self._parse_prominence(
                raw_cue.get("prominence"), f"distant_cues[{cue_id}].prominence"
            )
            ambient_descriptions = raw_cue.get("ambient_descriptions", {})
            if ambient_descriptions is None:
                ambient_descriptions = {}
            if not isinstance(ambient_descriptions, Mapping):
                raise ScenarioLoadError(
                    f"distant_cues[{cue_id}].ambient_descriptions must be an object"
                )
            appear_event = self._parse_distant_cue_appear_event(
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

    def _parse_distant_cue_appear_event(
        self,
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

    def _parse_distant_cue_source(
        self,
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
        if not self._is_json_primitive(equals):
            raise ScenarioLoadError(f"{path}.equals must be a JSON primitive")
        return DistantCueSourceDef(
            kind="object_state",
            object_id=object_id,
            state_key=state_key.strip(),
            equals=equals,
        )

    def _parse_distant_cue_origin_area_id(
        self,
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

    @staticmethod
    def _is_json_primitive(value: Any) -> bool:
        if value is None or isinstance(value, (str, bool)):
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return isfinite(value)
        return False

    def _spot_positions_by_area(
        self,
        spots_raw: Any,
    ) -> Dict[str, Tuple[SpotPosition, ...]]:
        grouped: Dict[str, List[SpotPosition]] = {}
        if not isinstance(spots_raw, Sequence) or isinstance(spots_raw, (str, bytes)):
            return {}
        for spot in spots_raw:
            if not isinstance(spot, Mapping):
                continue
            area_id = spot.get("area_id")
            if not isinstance(area_id, str) or not area_id.strip():
                continue
            position = self._parse_spot_position(
                str(spot.get("id", "<unknown>")),
                spot.get("position"),
            )
            if position is None:
                continue
            grouped.setdefault(area_id.strip(), []).append(position)
        return {area_id: tuple(positions) for area_id, positions in grouped.items()}

    @staticmethod
    def _area_centroid(positions: Sequence[SpotPosition]) -> Optional[SpotPosition]:
        if not positions:
            return None
        return SpotPosition(
            x=sum(p.x for p in positions) / len(positions),
            y=sum(p.y for p in positions) / len(positions),
        )

    def _parse_atmosphere(self, raw: Optional[Dict[str, Any]]) -> Optional[SpotAtmosphere]:
        if not raw:
            return None
        return SpotAtmosphere(
            lighting=LightingEnum[raw.get("lighting", "BRIGHT")],
            sound_ambient=raw.get("sound_ambient"),
            temperature=TemperatureEnum[raw.get("temperature", "NORMAL")],
            smell=raw.get("smell"),
        )

    def _parse_interior(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        remote_recorded_tick_keys: Mapping[int, frozenset[str]],
    ) -> SpotInterior:
        raw_objects = raw.get("objects", [])
        local_object_ids = {
            obj.get("id")
            for obj in raw_objects
            if isinstance(obj, dict) and isinstance(obj.get("id"), str)
        }
        sub_locs = tuple(
            self._parse_sub_location(
                s,
                mapper,
                local_object_ids=local_object_ids,
            )
            for s in raw.get("sub_locations", [])
        )
        objects = tuple(
            self._parse_spot_object(
                o,
                mapper,
                remote_recorded_tick_keys=remote_recorded_tick_keys,
            )
            for o in raw_objects
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

    def _parse_sub_location(
        self,
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
        dc = self._parse_discovery_condition(raw.get("discovery_condition"), mapper) if raw.get("discovery_condition") else None
        return SubLocation(
            sub_location_id=SubLocationId.create(sid),
            name=raw["name"],
            description=raw["description"],
            accessible_object_ids=obj_ids,
            is_hidden=_parse_bool(
                raw.get("is_hidden", False),
                path=f"sub_location {raw.get('id')}.is_hidden",
            ),
            discovery_condition=dc,
        )

    def _parse_spot_object(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        remote_recorded_tick_keys: Mapping[int, frozenset[str]],
    ) -> SpotObject:
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
        unavailable_hint = raw.get("unavailable_hint")
        if unavailable_hint is not None:
            if not isinstance(unavailable_hint, str) or not unavailable_hint.strip():
                raise ScenarioLoadError(
                    f"object {raw.get('id')}.unavailable_hint must be a non-empty string"
                )
        recorded_tick_state_keys = (
            _recorded_tick_state_keys(interactions, oid)
            | remote_recorded_tick_keys.get(oid, frozenset())
        )
        declared_hidden_state_keys = _parse_object_hidden_state_keys(raw)
        state_display = _parse_object_state_display(
            raw,
            recorded_tick_state_keys=recorded_tick_state_keys,
        )
        # 作家が明示した key に、手番を記録する効果が書く key を足す。
        # 名前を当てにいくのではなく、宣言から導出する (#949 写しは腐る)。
        hidden_state_keys = declared_hidden_state_keys | recorded_tick_state_keys
        return SpotObject(
            object_id=SpotObjectId.create(oid),
            name=raw["name"],
            description=raw["description"],
            object_type=SpotObjectTypeEnum[raw.get("object_type", "OTHER")],
            state=dict(raw.get("state", {})),
            interactions=interactions,
            description_variants=variants,
            is_visible=_parse_bool(
                raw.get("is_visible", True),
                path=f"object {raw.get('id')}.is_visible",
            ),
            is_visible_in_dark=_parse_bool(
                raw.get("is_visible_in_dark", False),
                path=f"object {raw.get('id')}.is_visible_in_dark",
            ),
            unavailable_hint=unavailable_hint,
            hidden_state_keys=hidden_state_keys,
            state_display=state_display,
        )

    def _parse_interaction_def(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        allow_target_notification: bool = False,
    ) -> InteractionDef:
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
        from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
            InteractionActorPlane,
        )

        action_name = raw.get("action_name")
        reserved_prefix = next(
            (
                prefix
                for prefix in (RESERVED_ACTION_NAME_PREFIX, ITEM_ACTION_NAME_PREFIX)
                if isinstance(action_name, str) and action_name.startswith(prefix)
            ),
            None,
        )
        if reserved_prefix is not None:
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].action_name は "
                f"'{reserved_prefix}' で始められません "
                f"(engine が待ち時間の記録に使う接頭辞です)"
            )
        display_label = raw.get("display_label")
        if not isinstance(display_label, str) or not display_label.strip():
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].display_label must be a non-empty string"
            )
        display_label = display_label.strip()

        preconds = tuple(
            self._parse_interaction_condition(c, mapper)
            for c in raw.get("preconditions", [])
        )
        effects = tuple(
            self._parse_interaction_effect(e, mapper) for e in raw.get("effects", [])
        )
        on_failure_observation = raw.get("on_failure_observation")
        witness_observation_message = raw.get("witness_observation_message")
        if (
            witness_observation_message is not None
            and not isinstance(witness_observation_message, str)
        ):
            raise ScenarioLoadError(
                f"interaction[{raw.get('action_name')!r}].witness_observation_message "
                f"must be a string, got {type(witness_observation_message).__name__}"
            )
        witness_observation_message_in_dark = raw.get(
            "witness_observation_message_in_dark"
        )
        if (
            witness_observation_message_in_dark is not None
            and not isinstance(witness_observation_message_in_dark, str)
        ):
            raise ScenarioLoadError(
                f"interaction[{raw.get('action_name')!r}]."
                "witness_observation_message_in_dark must be a string, got "
                f"{type(witness_observation_message_in_dark).__name__}"
            )
        # Phase G #1: witness_policy はオプション、デフォルト SAME_SPOT。
        # JSON で "ACTOR_ONLY" 等を文字列指定 → WitnessPolicy enum に変換。
        # 未知値は ScenarioLoadError で boundary fail (typo を早期検知)。
        witness_policy_raw = raw.get("witness_policy")
        if witness_policy_raw is None:
            witness_policy = WitnessPolicy.SAME_SPOT
        else:
            if not isinstance(witness_policy_raw, str):
                raise ScenarioLoadError(
                    f"interaction[{raw.get('action_name')!r}].witness_policy must be a string, "
                    f"got {type(witness_policy_raw).__name__}"
                )
            try:
                witness_policy = WitnessPolicy(witness_policy_raw)
            except ValueError as exc:
                valid = ", ".join(p.value for p in WitnessPolicy)
                raise ScenarioLoadError(
                    f"interaction[{raw.get('action_name')!r}].witness_policy "
                    f"must be one of {{{valid}}}, got {witness_policy_raw!r}"
                ) from exc
        notify_target, target_observation_message = self._parse_target_notification(
            raw, allow_target_notification=allow_target_notification
        )
        cooldown_ticks = self._parse_cooldown_ticks(raw)
        cooldown_group = self._parse_cooldown_group(raw)
        cooldown_scope = self._parse_cooldown_scope(raw)
        allowed_actor_planes_raw = raw.get("allowed_actor_planes", ["LIVING"])
        if not isinstance(allowed_actor_planes_raw, list) or not allowed_actor_planes_raw:
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].allowed_actor_planes は"
                "空でないリストで書いてください"
            )
        try:
            allowed_actor_planes = tuple(
                InteractionActorPlane(value) for value in allowed_actor_planes_raw
            )
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].allowed_actor_planes は "
                "LIVING / DEPARTED だけを指定できます"
            ) from exc
        if len(set(allowed_actor_planes)) != len(allowed_actor_planes):
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].allowed_actor_planes に重複があります"
            )
        hide_when_flag_preconditions_fail = _parse_bool(
            raw.get("hide_when_flag_preconditions_fail", False),
            path=(
                f"interaction[{action_name!r}]."
                "hide_when_flag_preconditions_fail"
            ),
        )
        if hide_when_flag_preconditions_fail and not any(
            condition.condition_type
            in (
                InteractionConditionTypeEnum.FLAG_SET,
                InteractionConditionTypeEnum.FLAG_NOT_SET,
            )
            for condition in preconds
        ):
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].hide_when_flag_preconditions_fail "
                "requires a FLAG_SET or FLAG_NOT_SET precondition"
            )
        return InteractionDef(
            action_name=raw["action_name"],
            display_label=display_label,
            preconditions=preconds,
            effects=effects,
            on_failure_observation=on_failure_observation,
            witness_observation_message=witness_observation_message,
            witness_observation_message_in_dark=(
                witness_observation_message_in_dark
            ),
            witness_policy=witness_policy,
            notify_target=notify_target,
            target_observation_message=target_observation_message,
            cooldown_ticks=cooldown_ticks,
            cooldown_group=cooldown_group,
            cooldown_scope=cooldown_scope,
            allowed_actor_planes=allowed_actor_planes,
            hide_when_flag_preconditions_fail=hide_when_flag_preconditions_fail,
        )

    @staticmethod
    def _parse_departed_agents_enabled(raw: Dict[str, Any]) -> bool:
        value = raw.get("departed_agents_enabled", False)
        if not isinstance(value, bool):
            raise ScenarioLoadError("departed_agents_enabled は真偽値で書いてください")
        return value

    @staticmethod
    def _parse_cooldown_group(raw: Any) -> Optional[str]:
        """複数の interaction が共有する待ち時間キーを読む。

        ``object:`` は物体操作の内部キーに予約済みなので、action_name と同じく
        シナリオには使わせない。対人・物体の記録が snapshot 上で衝突するのを
        読み込み時に止める。
        """
        value = raw.get("cooldown_group")
        if value is None:
            return None
        action_name = raw.get("action_name")
        if not isinstance(value, str) or not value.strip():
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].cooldown_group は"
                f"空でない文字列で書いてください: {value!r}"
            )
        value = value.strip()
        reserved_prefix = next(
            (
                prefix
                for prefix in (RESERVED_ACTION_NAME_PREFIX, ITEM_ACTION_NAME_PREFIX)
                if value.startswith(prefix)
            ),
            None,
        )
        if reserved_prefix is not None:
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].cooldown_group は "
                f"'{reserved_prefix}' で始められません "
                "(engine が待ち時間の記録に使う接頭辞です)"
            )
        return value

    @staticmethod
    def _parse_cooldown_ticks(raw: Any) -> int:
        """``cooldown_ticks`` を読む。省略時は 0 (制限しない)。

        負の値は拒否する。0 は正当な宣言 (制限しない) なので通す。
        真偽値は int の subclass なので明示的に弾く。``true`` と書いて
        1 tick になると、書いた人の意図と結果が食い違う。
        """
        value = raw.get("cooldown_ticks")
        if value is None:
            return 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise ScenarioLoadError(
                f"interaction[{raw.get('action_name')!r}].cooldown_ticks は"
                f"整数で書いてください: {value!r}"
            )
        if value < 0:
            raise ScenarioLoadError(
                f"interaction[{raw.get('action_name')!r}].cooldown_ticks は"
                f"0 以上で書いてください: {value}"
            )
        return value

    @staticmethod
    def _parse_cooldown_scope(raw: Any) -> InteractionCooldownScope:
        """待ち時間の共有単位を読み、未知値を actor へ黙って縮退させない。"""
        value = raw.get("cooldown_scope", InteractionCooldownScope.ACTOR.value)
        try:
            return InteractionCooldownScope(value)
        except (TypeError, ValueError) as exc:
            valid = ", ".join(scope.value for scope in InteractionCooldownScope)
            raise ScenarioLoadError(
                f"interaction[{raw.get('action_name')!r}].cooldown_scope は "
                f"{{{valid}}} のいずれかで書いてください: {value!r}"
            ) from exc

    @staticmethod
    def _parse_target_notification(
        raw: Dict[str, Any], *, allow_target_notification: bool,
    ) -> Tuple[bool, Optional[str]]:
        """``notify_target`` / ``target_observation_message`` を検証して返す。

        物体 interaction には対象プレイヤーが居ないので、書かれていたら落とす。
        黙って無視すると「対象に伝わるつもりで書いた宣言」が効かないまま残り、
        実 run で「なぜか相手が気づかない」としてしか現れない。
        """
        action_name = raw.get("action_name")
        notify_raw = raw.get("notify_target")
        message_raw = raw.get("target_observation_message")
        if notify_raw is None and message_raw is None:
            return False, None
        if not allow_target_notification:
            raise ScenarioLoadError(
                f"interaction[{action_name!r}]: notify_target / "
                "target_observation_message は対人 interaction "
                "(シナリオ直下の player_interactions) でのみ指定できます"
            )
        if notify_raw is not None and not isinstance(notify_raw, bool):
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].notify_target must be a boolean, "
                f"got {type(notify_raw).__name__}"
            )
        if message_raw is not None and not isinstance(message_raw, str):
            raise ScenarioLoadError(
                f"interaction[{action_name!r}].target_observation_message must be "
                f"a string, got {type(message_raw).__name__}"
            )
        notify_target = bool(notify_raw)
        if message_raw is not None and not notify_target:
            # 文面だけ書いて notify_target を立て忘れると、その文面はどこにも
            # 出ない。ACTOR_ONLY では対象に何も届かないままになる。
            raise ScenarioLoadError(
                f"interaction[{action_name!r}]: target_observation_message を"
                "書くなら notify_target=true が要ります "
                "(立てないと対象本人にはこの文面が届きません)"
            )
        return notify_target, message_raw

    def _parse_interaction_condition(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionCondition:
        item_sid = raw.get("required_item")
        item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
        obj_sid = raw.get("target_object")
        obj_id = SpotObjectId.create(mapper.get_int("object", obj_sid)) if obj_sid else None
        # 対象所持条件は、判定する品目の出所が要る。どちらも無いと条件は
        # 永久に不成立になり、interaction が黙って使えなくなる。実 run で
        # 「なぜか一度も成功しない」として初めて気付くことになるので、
        # 読み込み時に落とす。
        parameter_key = self._parse_item_spec_id_parameter_key(raw)
        if (
            raw.get("condition_type") in ("TARGET_HAS_ITEM", "TARGET_HAS_NO_ITEM")
            and parameter_key is None
            and item_spec_id is None
        ):
            raise ScenarioLoadError(
                f"{raw.get('condition_type')} requires either required_item or "
                "item_spec_id_parameter_key; どちらも無いと条件は常に不成立に"
                f"なります: {raw!r}"
            )
        required_lighting = self._parse_required_lighting(raw)
        required_spot_id = self._parse_required_spot_id(raw, mapper)
        if raw.get("condition_type") == "OBJECT_STATE_INT_AT_LEAST":
            state_key = raw.get("state_key")
            if not isinstance(state_key, str) or not state_key.strip():
                raise ScenarioLoadError(
                    "OBJECT_STATE_INT_AT_LEAST requires a non-empty state_key; "
                    f"無いと条件は常に不成立になります: {raw!r}"
                )
        # TARGET_PLAYER_STATE_IS は required_state が無いと常に不成立になる。
        if (
            raw.get("condition_type") == "TARGET_PLAYER_STATE_IS"
            and raw.get("required_state") is None
        ):
            raise ScenarioLoadError(
                "TARGET_PLAYER_STATE_IS requires required_state; "
                f"無いと条件は常に不成立になります: {raw!r}"
            )
        # 脱出ゲーム拡張フィールド
        required_items_raw = raw.get("required_items")
        required_item_spec_ids = None
        if required_items_raw:
            required_item_spec_ids = tuple(
                ItemSpecId.create(mapper.get_int("item_spec", s)) for s in required_items_raw
            )
        # 綴り間違いは enum 参照が KeyError で弾くが、**呼び出し側が捕まえて
        # いるのは ScenarioLoadError** なので、そのままだと読み込みの入口を
        # 素通りして生の KeyError が飛ぶ。行き先も示せない。
        raw_ctype = str(raw.get("condition_type", ""))
        try:
            ctype = InteractionConditionTypeEnum[raw_ctype]
        except KeyError as exc:
            raise ScenarioLoadError(
                f"condition_type '{raw_ctype}' は engine が知らない種類です。"
                f"使える種類: "
                f"{', '.join(sorted(c.name for c in InteractionConditionTypeEnum))}"
            ) from exc
        return InteractionCondition(
            condition_type=ctype,
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
            state_key=(
                raw.get("state_key", "").strip()
                if isinstance(raw.get("state_key"), str)
                else raw.get("state_key")
            ),
            need_type=self._parse_need_type(raw),
            need_threshold=raw.get("need_threshold"),
            hp_ratio=self._parse_hp_ratio(raw),
            # PR4: TIME_OF_DAY_IS{_NOT} / WEATHER_IS{_NOT} 用フィールド。
            # phase / weather_type は単純な文字列で受け取り、ランタイムで
            # 現在値と比較する。boundary 検証は別 PR で (現状 day_night の
            # phase 名はシナリオ宣言依存のため固定値リストを持たない)。
            required_time_of_day_phase=raw.get("required_time_of_day_phase"),
            required_weather_type=self._parse_required_weather_type(raw),
            # 対人 interaction: TARGET_HAS_ITEM / TARGET_HAS_NO_ITEM が判定
            # する品目を、interaction_parameters のどのキーから取るか。
            item_spec_id_parameter_key=parameter_key,
            # PR 3: 場所条件。SPOT_LIGHTING_IS{_NOT} / AT_SPOT_IS{_NOT} 用。
            required_lighting=required_lighting,
            required_spot_id=required_spot_id,
        )

    #: ``required_lighting`` / ``required_spot`` を書ける condition_type。
    #: これ以外に書かれていたら「書いたのに効かない」宣言なので落とす。
    _LIGHTING_CONDITIONS = ("SPOT_LIGHTING_IS", "SPOT_LIGHTING_IS_NOT")
    _AT_SPOT_CONDITIONS = ("AT_SPOT_IS", "AT_SPOT_IS_NOT")

    @classmethod
    def _parse_required_lighting(cls, raw: Dict[str, Any]) -> Optional[str]:
        """``required_lighting`` を検証して返す。

        値は ``LightingEnum`` のメンバ名に限る。タイポを実行時まで持ち越すと
        「照明が一致しないので不成立」と区別がつかず、シナリオ作者が書いた
        failure_message の裏にタイポが隠れる。
        """
        condition_type = raw.get("condition_type")
        value = raw.get("required_lighting")
        if value is None:
            if condition_type in cls._LIGHTING_CONDITIONS:
                raise ScenarioLoadError(
                    f"{condition_type} requires required_lighting; "
                    f"無いと条件は常に不成立になります: {raw!r}"
                )
            return None
        if condition_type not in cls._LIGHTING_CONDITIONS:
            raise ScenarioLoadError(
                f"required_lighting is only valid on {cls._LIGHTING_CONDITIONS}, "
                f"got condition_type={condition_type!r}: {raw!r}"
            )
        valid = tuple(level.value for level in LightingEnum)
        if value not in valid:
            raise ScenarioLoadError(
                f"required_lighting must be one of {valid}, got {value!r}: {raw!r}"
            )
        return value

    #: ``required_weather_type`` を書ける condition_type。
    _WEATHER_CONDITIONS = ("WEATHER_IS", "WEATHER_IS_NOT")

    @classmethod
    def _parse_required_weather_type(cls, raw: Dict[str, Any]) -> Optional[str]:
        """``required_weather_type`` を検証して返す。

        値は ``WeatherTypeEnum`` のメンバ名に限る。``required_lighting`` は既に
        この検証を持っていたが、**天候だけ素通りしていた**。素通りすると

        - 条件は永久に不成立になる (作者は「たまたま晴れないだけ」と読む)
        - ヒントに ``"METEOR_SHOWERのみ"`` と**内部識別子がプロンプトへ出る**

        の 2 つが同時に起きる。同じファイルの別機能 (line 3597 付近) も
        「WeatherTypeEnum 名は boundary で検証する (作家ミスを早期に弾く)」と
        しており、その方針をここへ揃える。
        """
        condition_type = raw.get("condition_type")
        value = raw.get("required_weather_type")
        if value is None:
            if condition_type in cls._WEATHER_CONDITIONS:
                raise ScenarioLoadError(
                    f"{condition_type} requires required_weather_type; "
                    f"無いと条件は常に不成立になります: {raw!r}"
                )
            return None
        valid = tuple(w.value for w in WeatherTypeEnum)
        if value not in valid:
            raise ScenarioLoadError(
                f"required_weather_type must be one of {valid}, got {value!r}: {raw!r}"
            )
        return value

    @classmethod
    def _parse_required_spot_id(
        cls, raw: Dict[str, Any], mapper: ScenarioIdMapper
    ) -> Optional[SpotId]:
        """``required_spot`` (シナリオ上の文字列 ID) を SpotId に解決する。"""
        condition_type = raw.get("condition_type")
        value = raw.get("required_spot")
        if value is None:
            if condition_type in cls._AT_SPOT_CONDITIONS:
                raise ScenarioLoadError(
                    f"{condition_type} requires required_spot; "
                    f"無いと条件は常に不成立になります: {raw!r}"
                )
            return None
        if condition_type not in cls._AT_SPOT_CONDITIONS:
            raise ScenarioLoadError(
                f"required_spot is only valid on {cls._AT_SPOT_CONDITIONS}, "
                f"got condition_type={condition_type!r}: {raw!r}"
            )
        # 未知のスポット ID は mapper が独自の例外を投げる。同じ「シナリオの
        # 書き間違い」なのに例外型が変わると、呼び出し側の except が漏れる。
        try:
            return SpotId.create(mapper.get_int("spot", str(value)))
        except ScenarioLoadError:
            raise
        except Exception as exc:
            raise ScenarioLoadError(
                f"required_spot={value!r} に対応する spot がシナリオにありません: {raw!r}"
            ) from exc

    @staticmethod
    def _parse_item_spec_id_parameter_key(raw: Dict[str, Any]) -> Optional[str]:
        """``item_spec_id_parameter_key`` を検証して返す。

        対象所持条件でしか意味を持たないフィールドなので、他の condition_type
        に書かれていたら黙って無視せず落とす。無視すると「書いたのに効かない」
        宣言がシナリオに残り、実 run で初めて気付くことになる。
        """
        key = raw.get("item_spec_id_parameter_key")
        if key is None:
            return None
        if not isinstance(key, str) or not key.strip():
            raise ScenarioLoadError(
                "item_spec_id_parameter_key must be a non-empty string"
            )
        cond_type = raw.get("condition_type")
        if cond_type not in ("TARGET_HAS_ITEM", "TARGET_HAS_NO_ITEM"):
            raise ScenarioLoadError(
                "item_spec_id_parameter_key is only valid on TARGET_HAS_ITEM / "
                f"TARGET_HAS_NO_ITEM (got condition_type={cond_type!r})"
            )
        return key.strip()

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

    # ``target=TARGET_PLAYER`` を受け付ける効果。ここに無い効果に対象を書いても
    # 意味を持たないので読み込み時に落とす (黙って ACTOR として動かすと、作者は
    # 対象へ効いたつもりのまま気づけない)。
    #
    # 選定の基準は「その効果が人に対して起きるか」。物体・通路・天候・世界フラグに
    # 効くものと、素材合成のように行為者の手元でしか成立しないものは除く。
    _TARGET_PLAYER_CAPABLE_EFFECTS = frozenset(
        {
            InteractionEffectTypeEnum.GIVE_ITEM,
            InteractionEffectTypeEnum.REMOVE_ITEM,
            InteractionEffectTypeEnum.APPLY_DAMAGE,
        }
    )

    # 「人に対して起きる効果」ではあるが、対象へ適用する配線がまだ無いもの。
    #
    # 宣言を許すと **行為者に効く**。ダメージ / 欲求 / state のバケットは
    # 行為者ぶんしか無く、``effect.target`` を見ずに積まれるためである。
    # 「相手を刺したつもりが自分が傷ついた」という、成功として返る最悪の
    # 誤動作になるので、配線が済むまでは読み込み時に落とす。
    #
    # ダメージ系を通すには、対象の ``PlayerDownedEvent`` を回収してキル判定を
    # 確定させる必要がある (docs/memory_system/interpersonal_interaction_design.md
    # の H-1)。これは別 PR。
    _TARGET_PLAYER_NOT_WIRED_YET = frozenset(
        {
            InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
            InteractionEffectTypeEnum.SATISFY_NEED,
            InteractionEffectTypeEnum.TELEPORT_ENTITY,
            InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
        }
    )

    def _parse_effect_target(
        self, raw: Dict[str, Any], *, actor_context: str
    ) -> EffectTarget:
        """``effects[].target`` を検証して返す。既定は行為者。

        3 種類の書き間違いを読み込み時に落とす。

        - 未知の値 (``"TARGET_PLAYERS"`` の綴り間違いが ``ACTOR`` に落ちると
          自分に致死ダメージが入る)
        - 対象を取れない効果への指定
        - 行為者が存在しない文脈での指定
        """
        raw_target = raw.get("target")
        if raw_target is None:
            return EffectTarget.ACTOR
        if isinstance(raw_target, EffectTarget):
            target = raw_target
        else:
            try:
                target = EffectTarget(raw_target)
            except (ValueError, TypeError):
                allowed = ", ".join(sorted(m.value for m in EffectTarget))
                raise ScenarioLoadError(
                    f"unknown effect target {raw_target!r}. "
                    f"使える値: {allowed}: {raw!r}"
                )
        if target is EffectTarget.ACTOR:
            return target

        if actor_context != "interaction":
            raise ScenarioLoadError(
                f"{actor_context} effects cannot use target=TARGET_PLAYER. "
                f"{actor_context} には行為者が存在せず、誰を対象にするか決まりません。"
                f"対人行為は interaction 側に書いてください: {raw!r}"
            )

        effect_type_str = raw.get("effect_type", "")
        try:
            effect_type = InteractionEffectTypeEnum[effect_type_str]
        except KeyError:
            # 未知の effect_type はこの関数の責務ではないので判断しない。
            # NOTE: 後段の ``InteractionEffectTypeEnum[raw["effect_type"]]`` は
            # try/except に包まれておらず、素の KeyError が load_from_dict から
            # 漏れる (ScenarioLoadError にはならない)。本 PR 以前からの挙動で、
            # 読み込みが失敗すること自体は変わらないが、loader の他のエラーと
            # 文面の質が揃っていない。統一は別 PR で。
            return target
        if effect_type in self._TARGET_PLAYER_NOT_WIRED_YET:
            raise ScenarioLoadError(
                f"{effect_type.name} with target=TARGET_PLAYER is declared but not "
                "wired yet; 宣言しても対象ではなく行為者に効いてしまうため、"
                "配線が済むまで受け付けません: "
                f"{raw!r}"
            )
        if effect_type not in self._TARGET_PLAYER_CAPABLE_EFFECTS:
            capable = ", ".join(
                sorted(e.name for e in self._TARGET_PLAYER_CAPABLE_EFFECTS)
            )
            raise ScenarioLoadError(
                f"{effect_type.name} does not support target=TARGET_PLAYER. "
                f"対象を取れる効果: {capable}: {raw!r}"
            )
        return target

    def _parse_interaction_effect(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        actor_context: str = "interaction",
    ) -> InteractionEffect:
        """効果 1 件をパースする。

        ``actor_context`` は「この効果が誰の行為として適用されるか」を表す。
        ``interaction`` 以外 (scenario_event / synchronized_action_group) には
        行為者が存在せず、``target=TARGET_PLAYER`` を書いても誰を対象にするか
        決まらない。書けるのに何も起きない状態を残さないため、その文脈では
        読み込み時に落とす。
        """
        params = dict(raw.get("parameters", {}))
        effect_type_str = raw.get("effect_type", "")
        if (
            actor_context == "scenario_event"
            and effect_type_str == InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK.name
        ):
            raise ScenarioLoadError(
                "scenario_event effects cannot use RECORD_PLAYER_STATE_TICK. "
                "scenario_event には行為者が存在せず、誰の state に手番を記録するか"
                f"決まりません: {raw!r}"
            )
        # Phase 4-E: visibility は parameters dict ではなく first-class 属性で
        # 持つ。トップレベル "visibility" を優先し、過渡期サポートとして
        # parameters["visibility"] からも吸い上げる。両方あったら top-level 優先。
        visibility_raw = raw.get("visibility")
        if visibility_raw is None and "visibility" in params:
            visibility_raw = params.pop("visibility")
        else:
            params.pop("visibility", None)
        visibility: Optional[EffectVisibility] = None
        if isinstance(visibility_raw, EffectVisibility):
            visibility = visibility_raw
        elif isinstance(visibility_raw, str) and visibility_raw:
            try:
                visibility = EffectVisibility(visibility_raw)
            except ValueError:
                # 値の妥当性は runtime 側でも警告ログを出すが、
                # ここは「読み込めなかった」状態を残さず None に倒し
                # 既定値が使われるようにする。
                visibility = None
        target = self._parse_effect_target(raw, actor_context=actor_context)
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
        if "loot_table" in params:
            # PR #1: "loot_table" 文字列 id → numeric loot_table_id へ正規化
            params["loot_table_id"] = mapper.get_int(
                "loot_table", params.pop("loot_table"),
            )
        effect_type = InteractionEffectTypeEnum[raw["effect_type"]]
        if effect_type is InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION:
            flag = params.get("flag")
            if not isinstance(flag, str) or not flag.strip():
                raise ScenarioLoadError(
                    "RESOLVE_ONGOING_CONDITION requires parameters.flag"
                )
            params["flag"] = flag.strip()
        if (
            effect_type is InteractionEffectTypeEnum.SHOW_ROOM_OCCUPANCY
            and actor_context != "interaction"
        ):
            raise ScenarioLoadError(
                "SHOW_ROOM_OCCUPANCY requires an acting player and is only valid "
                f"in interactions: actor_context={actor_context!r}"
            )
        if effect_type is InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT:
            if actor_context != "interaction":
                raise ScenarioLoadError(
                    "DEPOSIT_ITEM_TO_OBJECT requires an acting player and is only "
                    f"valid in interactions: actor_context={actor_context!r}"
                )
            if "item_spec_id" not in params:
                raise ScenarioLoadError(
                    "DEPOSIT_ITEM_TO_OBJECT requires parameters.item_spec"
                )
            state_key = params.get("state_key")
            if not isinstance(state_key, str) or not state_key.strip():
                raise ScenarioLoadError(
                    "DEPOSIT_ITEM_TO_OBJECT requires parameters.state_key"
                )
            params["state_key"] = state_key.strip()
            if "quantity" not in params:
                raise ScenarioLoadError(
                    "DEPOSIT_ITEM_TO_OBJECT requires parameters.quantity; "
                    "正の整数または 'all' を明示してください"
                )
            quantity = params["quantity"]
            if quantity != "all" and (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or quantity <= 0
            ):
                raise ScenarioLoadError(
                    "DEPOSIT_ITEM_TO_OBJECT parameters.quantity must be a "
                    f"positive integer or 'all' (got {quantity!r})"
                )
        if effect_type is InteractionEffectTypeEnum.CALL_MEETING:
            trigger = params.get("trigger")
            if trigger not in CALL_MEETING_EFFECT_TRIGGERS:
                raise ScenarioLoadError(
                    "CALL_MEETING parameters.trigger must be one of "
                    f"{sorted(CALL_MEETING_EFFECT_TRIGGERS)!r} "
                    f"(got {trigger!r})"
                )
        # TELEPORT_ENTITY は行き先が無いと domain 側で「spot_id <= 0 なら spec を
        # 作らない」に落ち、書いたのに何も起きない静かな失敗になる。行き先は
        # ``parameters.target_spot`` に書く決まりで、effect の直下に書いても
        # params には載らない (= 無言で消える) ため、ここで弾いて起動時に気づける
        # ようにする。
        if effect_type is InteractionEffectTypeEnum.TELEPORT_ENTITY:
            if "spot_id" not in params:
                raise ScenarioLoadError(
                    "TELEPORT_ENTITY effect requires parameters.target_spot "
                    "(移動先の spot id)。effect の直下ではなく parameters の中に "
                    f"書いてください: {raw!r}"
                )
            # TELEPORT_ENTITY の観測は「出発スポットと到着スポットに誰が居たか」
            # だけで決まる (EntityLeftSpotEvent / EntityEnteredSpotEvent)。
            # visibility を書いても移動の見え方は変わらないので、書けば効くと
            # 誤解したまま HIDDEN な移動を期待されるより、読み込み時に落とす。
            if visibility is not None:
                raise ScenarioLoadError(
                    "TELEPORT_ENTITY effect does not support 'visibility'. "
                    "移動が見えるかは出発・到着スポットに誰が居たかだけで決まる "
                    "(誰も居なければ誰にも観測されない)。"
                    f"visibility を外してください: {raw!r}"
                )
            self._validate_teleport_observation_messages(params, raw)
        # CHANGE_ATMOSPHERE も同型の静かな失敗を持つ。対象 spot が無いと domain 側
        # は spec を作らず、enum 名の綴りを間違えても実行時まで気づけない。
        if effect_type is InteractionEffectTypeEnum.CHANGE_ATMOSPHERE:
            self._validate_change_atmosphere_params(params, raw)
        return InteractionEffect(
            effect_type=effect_type,
            parameters=params,
            visibility=visibility,
            target=target,
        )


    #: TELEPORT_ENTITY の parameters に書ける鍵。ここに無い綴りは読み込み時に落とす。
    _TELEPORT_PARAM_KEYS = frozenset(
        {
            "spot_id",
            "departure_observation_message",
            "departure_observation_message_in_dark",
            "arrival_observation_message",
            "arrival_observation_message_in_dark",
        }
    )
    #: 観測文で展開できるプレースホルダ。formatter がこれしか置換しない。
    _TELEPORT_MESSAGE_PLACEHOLDERS = frozenset({"{actor}"})

    @classmethod
    def _validate_teleport_observation_messages(
        cls, params: Dict[str, Any], raw: Dict[str, Any]
    ) -> None:
        """観測文の宣言ミスを起動時に落とす。

        **静かに既定文へ縮退する経路を塞ぐ。** 綴り違いの鍵は誰も読まず、
        非文字列は None へ落ち、未知のプレースホルダは展開されないまま出る。
        どれも「書いたのに効かない」形で、対象 spot の欠落を落としているのと
        同じ理由でここで止める。

        空文字も拒否する。formatter は空文字を「宣言なし」として既定文へ戻すので、
        「宣言したが空」を運ぶことはできない。**意味を一方へ揃える。**
        """
        unknown = sorted(set(params) - cls._TELEPORT_PARAM_KEYS)
        if unknown:
            raise ScenarioLoadError(
                f"TELEPORT_ENTITY effect has unknown parameters {unknown}. "
                f"書ける鍵は {sorted(cls._TELEPORT_PARAM_KEYS)} です "
                f"(綴り違いは黙って無視され、既定文へ縮退します): {raw!r}"
            )
        for key in cls._TELEPORT_PARAM_KEYS - {"spot_id"}:
            if key not in params:
                continue
            value = params[key]
            if not isinstance(value, str):
                raise ScenarioLoadError(
                    f"TELEPORT_ENTITY effect parameter '{key}' must be a string "
                    f"(got {value!r})。非文字列は黙って既定文へ縮退します: {raw!r}"
                )
            if not value.strip():
                raise ScenarioLoadError(
                    f"TELEPORT_ENTITY effect parameter '{key}' must not be empty。"
                    "空文字は既定文と区別できません。出したくないなら鍵ごと "
                    f"外してください: {raw!r}"
                )
            # **閉じた {...} だけを見てはいけない。** `{actor` や `actor}` は
            # 波括弧が揃わないので検出をすり抜け、formatter も完全一致しか
            # 置換しないため未展開のまま観測へ出る。{Actor} と同じ静かな誤記。
            # 波括弧を 1 つでも含むなら、既知の placeholder だけで構成されて
            # いることを要求する。
            if "{" in value or "}" in value:
                remainder = value
                for known in cls._TELEPORT_MESSAGE_PLACEHOLDERS:
                    remainder = remainder.replace(known, "")
                if "{" in remainder or "}" in remainder:
                    raise ScenarioLoadError(
                        f"TELEPORT_ENTITY effect parameter '{key}' has a brace that "
                        f"is not a known placeholder ({value!r})。展開されるのは "
                        f"{sorted(cls._TELEPORT_MESSAGE_PLACEHOLDERS)} だけで、"
                        f"閉じ忘れや綴り違いはそのまま観測へ出ます: {raw!r}"
                    )

    @staticmethod
    def _validate_change_atmosphere_params(
        params: Dict[str, Any], raw: Dict[str, Any]
    ) -> None:
        """CHANGE_ATMOSPHERE の対象 spot と enum 値を読み込み時に検証する。

        domain 側は ``spot_id <= 0`` なら spec を作らず、``lighting`` /
        ``temperature`` の文字列も application 層で enum へ引き当てるまで
        妥当性が分からない。放置すると「JSON に書いたのに照明が落ちない」
        「綴りを間違えたまま気づかない」静かな失敗になるので、ここで弾く。
        """
        if "spot_id" not in params:
            raise ScenarioLoadError(
                "CHANGE_ATMOSPHERE effect requires parameters.target_spot "
                "(環境を変える spot id)。effect の直下ではなく parameters の中に "
                f"書いてください: {raw!r}"
            )

        for key, enum_cls in (
            ("lighting", LightingEnum),
            ("temperature", TemperatureEnum),
        ):
            value = params.get(key)
            if value is None:
                continue
            if value not in enum_cls.__members__:
                allowed = ", ".join(sorted(enum_cls.__members__))
                raise ScenarioLoadError(
                    f"CHANGE_ATMOSPHERE effect has unknown {key} {value!r}. "
                    f"使える値: {allowed}: {raw!r}"
                )

        changed = [
            key
            for key in ("lighting", "temperature", "hazard_level", "hazard_description")
            if params.get(key) is not None
        ]
        if not changed:
            raise ScenarioLoadError(
                "CHANGE_ATMOSPHERE effect changes nothing. "
                "lighting / temperature / hazard_level / hazard_description の "
                f"いずれかを parameters に書いてください: {raw!r}"
            )

    def _parse_scenario_events(
        self,
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
                self._parse_scenario_event_condition(
                    c, mapper, path=f"scenario_event[{event_id}].conditions[{i}]",
                )
                for i, c in enumerate(raw.get("conditions", []))
            )
            effects = tuple(
                self._parse_interaction_effect(
                    e, mapper, actor_context="scenario_event",
                )
                for e in raw.get("effects", [])
            )
            parsed.append(
                ScenarioEventDef(
                    event_id=event_id,
                    trigger=trigger,
                    once=_parse_bool(
                        raw.get("once", True),
                        path=f"scenario_event[{event_id}].once",
                    ),
                    conditions=conditions,
                    effects=effects,
                    observation_category=str(observation.get("category", "environment")),
                    recipients=recipients,
                    target_spot_id=self._optional_spot_id(target_spot, mapper),
                    schedules_turn=_parse_bool(
                        observation.get("schedules_turn", True),
                        path=(
                            f"scenario_event[{event_id}].observation.schedules_turn"
                        ),
                    ),
                    breaks_movement=_parse_bool(
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

    def _parse_player_outcome_rules(
        self,
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
                        trigger=self._parse_scenario_event_condition(
                            trigger_raw,
                            mapper,
                            path=f"{path}.trigger",
                        ),
                        player_conditions=tuple(
                            self._parse_scenario_event_condition(
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
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"{path} must be a condition object "
                f"(got {type(raw).__name__})"
            )
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
                self._parse_scenario_event_condition(
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
                treat_missing_as_passed=_parse_bool(
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
            apply_to_reverse = _parse_bool(
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

    def _parse_player_interactions(
        self, raw_list: Any, mapper: ScenarioIdMapper,
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

            idef = self._parse_interaction_def(
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

    def _reject_unreachable_synchronized_action_names(
        self,
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
        declared = self._declared_action_names(raw)
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

    @staticmethod
    def _declared_action_names(raw: Dict[str, Any]) -> Set[str]:
        """シナリオ生データから、宣言済みの `action_name` を全部集める。"""
        names: Set[str] = set()

        def add_from(interactions: Any) -> None:
            if not isinstance(interactions, list):
                return
            for entry in interactions:
                if isinstance(entry, dict) and entry.get("action_name"):
                    names.add(str(entry["action_name"]))

        for spot in raw.get("spots", []) or []:
            if not isinstance(spot, dict):
                continue
            add_from(spot.get("interactions"))
            interior = spot.get("interior") or {}
            if isinstance(interior, dict):
                for obj in interior.get("objects", []) or []:
                    if isinstance(obj, dict):
                        add_from(obj.get("interactions"))
        for connection in raw.get("connections", []) or []:
            if isinstance(connection, dict):
                add_from(connection.get("interactions"))
        add_from(raw.get("player_interactions"))
        return names

    def _parse_synchronized_action_groups(
        self, raw: Any, mapper: ScenarioIdMapper,
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
                self._parse_interaction_effect(
                    e, mapper, actor_context="synchronized_action_group",
                )
                for e in g.get("on_complete", [])
            )
            on_timeout = tuple(
                self._parse_interaction_effect(
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

    def _parse_day_night_config(
        self, raw: Dict[str, Any],
    ) -> Optional[ScenarioDayNightConfig]:
        """`environment.day_night` を読んで DayNightCycleDef を組み立てる。

        JSON 形式 (シナリオ作家向け契約):
        ```
        "environment": {
            "day_night": {
                "enabled": true,
                "ticks_per_day": 24,
                "starting_tick_in_day": 0,
                "announce_changes": true,
                "phases": [
                    {"name": "morning", "start_ratio": 0.0,  "display_text": "朝",   "ambient_light": 0.9, "is_dark": false},
                    {"name": "noon",    "start_ratio": 0.25, "display_text": "昼",   "ambient_light": 1.0, "is_dark": false},
                    {"name": "evening", "start_ratio": 0.5,  "display_text": "夕暮れ","ambient_light": 0.5, "is_dark": false},
                    {"name": "night",   "start_ratio": 0.66, "display_text": "夜",   "ambient_light": 0.1, "is_dark": true}
                ]
            }
        }
        ```

        - `enabled: false` または `day_night` セクション自体が無い場合は None を返し、
          runtime は昼夜サイクルを動かさない (常に時刻表示なし)
        - フェーズ列の昇順性などのバリデーションは DayNightCycleDef.__post_init__
          に任せる (作家ミスは boundary で弾く)
        """
        day_night = raw.get("day_night") if isinstance(raw, dict) else None
        if not isinstance(day_night, dict):
            return None
        if not _parse_bool(
            day_night.get("enabled", False),
            path="environment.day_night.enabled",
        ):
            return None

        # 漂流島 v2 で導入された「1 tick = 1 時間」スケールに合わせ default=24
        # (旧 default=12 は monster_behavior_world_port:196 の hardcode=24 と
        # 不整合で、ticks_per_day を省略したシナリオの day_night phase 判定が
        # 2 倍速で進む silent failure を生んでいた)
        ticks_per_day = int(day_night.get("ticks_per_day", 24))
        starting_tick = int(day_night.get("starting_tick_in_day", 0))
        announce = _parse_bool(
            day_night.get("announce_changes", True),
            path="environment.day_night.announce_changes",
        )
        phases_raw = day_night.get("phases", [])
        if not isinstance(phases_raw, list) or not phases_raw:
            raise ScenarioLoadError(
                "environment.day_night.phases must be a non-empty list"
            )
        required_keys = ("name", "start_ratio", "display_text", "ambient_light", "is_dark")
        phases_list: list[DayNightPhaseDef] = []
        for i, p in enumerate(phases_raw):
            # boundary 検証: 各要素が dict で必須キーを持っているかを scenario_loader
            # 層で弾く。これを怠ると未定義キーで KeyError が ScenarioLoadError を
            # 経由せず素通りし、作家へのエラーメッセージが分かりにくくなる。
            if not isinstance(p, dict):
                raise ScenarioLoadError(
                    f"environment.day_night.phases[{i}] must be an object, "
                    f"got {type(p).__name__}"
                )
            missing = [k for k in required_keys if k not in p]
            if missing:
                raise ScenarioLoadError(
                    f"environment.day_night.phases[{i}] is missing required keys: {missing}"
                )
            phases_list.append(
                DayNightPhaseDef(
                    name=str(p["name"]),
                    start_ratio=float(p["start_ratio"]),
                    display_text=str(p["display_text"]),
                    ambient_light=float(p["ambient_light"]),
                    is_dark=_parse_bool(
                        p["is_dark"],
                        path=f"environment.day_night.phases[{i}].is_dark",
                    ),
                )
            )
        phases = tuple(phases_list)
        cycle = DayNightCycleDef(
            ticks_per_day=ticks_per_day,
            starting_tick_in_day=starting_tick,
            phases=phases,
        )
        return ScenarioDayNightConfig(cycle=cycle, announce_changes=announce)

    def _parse_monsters_block(
        self, raw: Optional[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> Tuple[Tuple[ScenarioMonsterTemplate, ...], Tuple[ScenarioMonsterPlacement, ...]]:
        """`monsters.templates` と `monsters.initial_placements` を読み込む (Phase B-2a)。

        JSON 形式:
        ```
        "monsters": {
          "templates": [
            {
              "id": "wild_dog",
              "name": "野犬",
              "description": "...",
              "race": "WOLF",                  // Race enum 名
              "faction": "ENEMY",              // MonsterFactionEnum 名
              "base_stats": {                  // 必須キー全部
                "max_hp": 30, "max_mp": 0, "attack": 8, "defense": 4,
                "speed": 6, "critical_rate": 0.05, "evasion_rate": 0.1
              },
              "reward": {"exp": 10, "gold": 0},
              "respawn": {"interval_ticks": 50, "auto": true},
              "vision_range": 4,
              "flee_threshold": 0.2
            }
          ],
          "initial_placements": [
            {"template": "wild_dog", "spot": "deep_forest", "coordinate": {"x": 0, "y": 0}}
          ]
        }
        ```

        Phase B-2a では initial_placements は static (シナリオ起動時のみ配置)。
        spawn_condition による動的 spawn は Phase B-2b で扱う。
        """
        if not isinstance(raw, dict):
            return ((), ())
        templates_raw = raw.get("templates", [])
        placements_raw = raw.get("initial_placements", [])
        if not isinstance(templates_raw, list):
            raise ScenarioLoadError("monsters.templates must be a list")
        if not isinstance(placements_raw, list):
            raise ScenarioLoadError("monsters.initial_placements must be a list")

        templates = tuple(
            self._parse_monster_template(t, mapper, i)
            for i, t in enumerate(templates_raw)
        )
        placements = tuple(
            self._parse_monster_placement(p, i)
            for i, p in enumerate(placements_raw)
        )
        return templates, placements

    def _parse_monster_template(
        self, raw: Any, mapper: ScenarioIdMapper, index: int,
    ) -> ScenarioMonsterTemplate:
        """1 monster template を MonsterTemplate に変換する。"""
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"monsters.templates[{index}] must be an object, got {type(raw).__name__}"
            )
        string_id = raw.get("id")
        if not isinstance(string_id, str) or not string_id:
            raise ScenarioLoadError(
                f"monsters.templates[{index}].id must be a non-empty string"
            )
        # 文字列 ID → 連番 int を id_mapper に登録 (将来 cross-reference する場面用)
        template_int_id = mapper.register("monster_template", string_id)

        base = raw.get("base_stats", {})
        if not isinstance(base, dict):
            raise ScenarioLoadError(
                f"monsters.templates[{index}].base_stats must be an object"
            )
        try:
            base_stats = BaseStats(
                max_hp=int(base.get("max_hp", 30)),
                max_mp=int(base.get("max_mp", 0)),
                attack=int(base.get("attack", 5)),
                defense=int(base.get("defense", 3)),
                speed=int(base.get("speed", 5)),
                critical_rate=float(base.get("critical_rate", 0.05)),
                evasion_rate=float(base.get("evasion_rate", 0.05)),
            )
        except (TypeError, ValueError) as e:
            raise ScenarioLoadError(
                f"monsters.templates[{index}].base_stats parse error: {e}"
            ) from e

        reward_raw = raw.get("reward", {})
        reward = RewardInfo(
            exp=int(reward_raw.get("exp", 0)),
            gold=int(reward_raw.get("gold", 0)),
        )
        respawn_raw = raw.get("respawn", {})
        respawn = RespawnInfo(
            respawn_interval_ticks=int(respawn_raw.get("interval_ticks", 50)),
            is_auto_respawn=_parse_bool(
                respawn_raw.get("auto", True),
                path=f"monsters.templates[{index}].respawn.auto",
            ),
        )

        race_name = str(raw.get("race", "WOLF"))
        try:
            race = Race[race_name]
        except KeyError as e:
            valid = [r.name for r in Race]
            raise ScenarioLoadError(
                f"monsters.templates[{index}].race must be one of {valid}, got {race_name}"
            ) from e
        faction_name = str(raw.get("faction", "ENEMY"))
        try:
            faction = MonsterFactionEnum[faction_name]
        except KeyError as e:
            valid = [f.name for f in MonsterFactionEnum]
            raise ScenarioLoadError(
                f"monsters.templates[{index}].faction must be one of {valid}, got {faction_name}"
            ) from e

        template = MonsterTemplate(
            template_id=MonsterTemplateId(template_int_id),
            name=str(raw.get("name", string_id)),
            base_stats=base_stats,
            reward_info=reward,
            respawn_info=respawn,
            race=race,
            faction=faction,
            description=str(raw.get("description", "")),
            skill_ids=[],  # Phase B-2a ではスキル無し
            vision_range=int(raw.get("vision_range", 5)),
            flee_threshold=float(raw.get("flee_threshold", 0.2)),
            attack_status_effects=self._parse_monster_attack_status_effects(
                raw.get("attack_status_effects", []), index,
            ),
        )
        return ScenarioMonsterTemplate(string_id=string_id, template=template)

    def _parse_monster_attack_status_effects(
        self, raw: Any, template_index: int,
    ) -> tuple[AttackStatusEffectChance, ...]:
        """攻撃時状態異常のJSON宣言を、検証済みドメイン値へ変換する。"""
        path = f"monsters.templates[{template_index}].attack_status_effects"
        if not isinstance(raw, list):
            raise ScenarioLoadError(f"{path} must be a list")
        parsed: list[AttackStatusEffectChance] = []
        for effect_index, item in enumerate(raw):
            item_path = f"{path}[{effect_index}]"
            if not isinstance(item, dict):
                raise ScenarioLoadError(f"{item_path} must be an object")
            effect_type_raw = item.get("effect_type")
            try:
                effect_type = StatusEffectType(effect_type_raw)
            except (TypeError, ValueError) as exc:
                raise ScenarioLoadError(
                    f"{item_path}.effect_type must be a StatusEffectType value, "
                    f"got {effect_type_raw!r}"
                ) from exc
            try:
                parsed.append(AttackStatusEffectChance(
                    effect_type=effect_type,
                    chance=item.get("chance"),
                    duration_ticks=item.get("duration_ticks"),
                    value=item.get("value", 1.0),
                ))
            except MonsterTemplateValidationException as exc:
                raise ScenarioLoadError(f"{item_path}: {exc}") from exc
        return tuple(parsed)

    def _parse_monster_placement(
        self, raw: Any, index: int,
    ) -> ScenarioMonsterPlacement:
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"monsters.initial_placements[{index}] must be an object"
            )
        template_id = raw.get("template")
        spot_id = raw.get("spot")
        if not isinstance(template_id, str) or not template_id:
            raise ScenarioLoadError(
                f"monsters.initial_placements[{index}].template must be a non-empty string"
            )
        if not isinstance(spot_id, str) or not spot_id:
            raise ScenarioLoadError(
                f"monsters.initial_placements[{index}].spot must be a non-empty string"
            )
        coord = raw.get("coordinate", {})
        if not isinstance(coord, dict):
            coord = {}
        spawn_condition = self._parse_monster_spawn_condition(
            raw.get("spawn_condition"), index,
        )
        return ScenarioMonsterPlacement(
            template_string_id=template_id,
            spot_string_id=spot_id,
            coordinate_x=int(coord.get("x", 0)),
            coordinate_y=int(coord.get("y", 0)),
            coordinate_z=int(coord.get("z", 0)),
            spawn_condition=spawn_condition,
        )

    def _parse_monster_spawn_condition(
        self, raw: Any, placement_index: int,
    ) -> Optional[ScenarioMonsterSpawnCondition]:
        """placement の spawn_condition ブロックを ScenarioMonsterSpawnCondition に変換。

        JSON 形式:
        ```
        "spawn_condition": {
          "day_night_phases": ["night"],
          "required_flags": ["high_tide"],
          "forbidden_flags": [],
          "weather_types": ["STORM"]
        }
        ```
        いずれか 1 つでも軸が指定されれば条件付き。すべて空 / セクション欠落
        なら null を返し、placement は常時 spawn (static) 扱い。

        WeatherTypeEnum 名は boundary で検証する (作家ミスを早期に弾く)。
        day_night_phases は scenario 内で自由命名できるので事前検証しない。
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"monsters.initial_placements[{placement_index}].spawn_condition "
                f"must be an object, got {type(raw).__name__}"
            )
        unknown_keys = set(raw) - set(
            _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS
        )
        if unknown_keys:
            raise ScenarioLoadError(
                f"monsters.initial_placements[{placement_index}].spawn_condition "
                f"contains unknown keys: {sorted(unknown_keys)}"
            )

        def _as_str_tuple(value: Any, key: str) -> Tuple[str, ...]:
            if value is None:
                return ()
            if not isinstance(value, list):
                raise ScenarioLoadError(
                    f"monsters.initial_placements[{placement_index}]."
                    f"spawn_condition.{key} must be a list of strings"
                )
            return tuple(str(v) for v in value)

        values = {
            key: _as_str_tuple(raw.get(key), key)
            for key in _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS
        }
        phases = values["day_night_phases"]
        required_flags = values["required_flags"]
        forbidden_flags = values["forbidden_flags"]
        weathers = values["weather_types"]

        # WeatherTypeEnum 名は事前検証する。作家ミスは boundary で弾く。
        for w in weathers:
            try:
                WeatherTypeEnum[w]
            except KeyError as e:
                valid = [x.name for x in WeatherTypeEnum]
                raise ScenarioLoadError(
                    f"monsters.initial_placements[{placement_index}]."
                    f"spawn_condition.weather_types contains invalid value {w!r}. "
                    f"Valid values: {valid}"
                ) from e

        return ScenarioMonsterSpawnCondition(
            day_night_phase_names=phases,
            required_flags=required_flags,
            forbidden_flags=forbidden_flags,
            weather_type_names=weathers,
        )

    def _parse_weather_config(self, raw: Dict[str, Any]) -> Optional[ScenarioWeatherConfig]:
        weather = raw.get("weather") if isinstance(raw, dict) else None
        if not isinstance(weather, dict):
            return None
        enabled = _parse_bool(
            weather.get("enabled", False),
            path="environment.weather.enabled",
        )
        initial = weather.get("initial", {})
        if not isinstance(initial, dict):
            initial = {}
        weather_type = WeatherTypeEnum[str(initial.get("weather_type", "FOG"))]
        intensity = float(initial.get("intensity", 0.6))
        return ScenarioWeatherConfig(
            enabled=enabled,
            initial_state=WeatherState(weather_type=weather_type, intensity=intensity),
            update_interval_ticks=int(weather.get("update_interval_ticks", 6)),
            announce_changes=_parse_bool(
                weather.get("announce_changes", True),
                path="environment.weather.announce_changes",
            ),
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
            consume_item=_parse_bool(
                raw.get("consume_item", False),
                path="passage_condition.consume_item",
            ),
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
            is_bidir = _parse_bool(
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

    def _parse_players(
        self, players_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> List[PlayerSpawnConfig]:
        spawns: List[PlayerSpawnConfig] = []
        for p in players_raw:
            pid = mapper.register("player", p["id"])
            spot_sid = p["spawn_spot"]
            spot_id = SpotId.create(mapper.get_int("spot", spot_sid))
            items = tuple(
                self._parse_initial_item(raw, mapper, owner_id=p["id"])
                for raw in p.get("initial_items", [])
            )
            initial_state = self._parse_player_initial_state(
                p.get("initial_state", {}), owner_id=p["id"],
            )
            persona_raw = p.get("persona_prompt")
            persona_prompt: Optional[str] = None
            if persona_raw is not None:
                if not isinstance(persona_raw, str):
                    raise ValueError(
                        f"player '{p['id']}': persona_prompt must be a string, "
                        f"got {type(persona_raw).__name__}"
                    )
                # 前後 whitespace を削るが内側の改行は保持する (多行プロンプトを許容)
                stripped = persona_raw.strip()
                persona_prompt = stripped if stripped else None
            objective = self._parse_player_objective(
                p.get("objective"), owner_id=p["id"],
            )
            goal_locked = self._parse_player_goal_locked(
                p.get("goal_locked"), owner_id=p["id"],
            )
            initial_gold = self._parse_player_initial_gold(
                p.get("initial_gold"), owner_id=p["id"],
            )
            spawns.append(PlayerSpawnConfig(
                string_id=p["id"],
                player_id=pid,
                name=p["name"],
                spawn_spot_id=spot_id,
                initial_items=items,
                initial_state=initial_state,
                persona_prompt=persona_prompt,
                objective=objective,
                goal_locked=goal_locked,
                initial_gold=initial_gold,
            ))
        return spawns

    @staticmethod
    def _parse_player_initial_gold(raw: Any, *, owner_id: str) -> int:
        """``players[].initial_gold`` を検証する (経済統合 Phase 0)。

        省略は「無一文で始まる」と同義なので 0 に畳む。負値は Gold 値
        オブジェクトの下限 0 に反するため、実行前に落とす。bool を除くのは
        True が int として通ると 1 gold の宣言と見分けが付かなくなるため。
        """
        if raw is None:
            return 0
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_gold は整数で宣言してください "
                f"(got {raw!r})"
            )
        if raw < 0:
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_gold は 0 以上で宣言してください "
                f"(got {raw})"
            )
        return raw

    @staticmethod
    def _parse_player_objective(raw: Any, *, owner_id: str) -> Optional[str]:
        """``players[].objective`` を検証して正規化する (目的層 G6)。

        persona_prompt と同じ規約: 前後の whitespace は削るが内側の改行は
        保持する (箇条書きの目的文を許容するため)。空文字・空白のみは None に
        畳んで「未指定」と同じ扱いにする — 空文字で seed すると GoalEntry の
        VO 不変条件に弾かれて静かに目的が消えるため、入口で潰す。
        """
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ValueError(
                f"player '{owner_id}': objective must be a string, "
                f"got {type(raw).__name__}"
            )
        stripped = raw.strip()
        if not stripped:
            # 空白のみを黙って None に畳むと「個別目的を書いたつもりが共通目的で
            # seed される」静かな失敗になる。共通目的文が非空の通常シナリオでは
            # fail-fast にも掛からないので、ここで痕跡を残すしかない。
            logging.getLogger(__name__).warning(
                "player '%s': objective is whitespace-only; treating it as unset "
                "and falling back to metadata.llm_objective_text",
                owner_id,
            )
            return None
        return stripped

    @staticmethod
    def _parse_player_goal_locked(raw: Any, *, owner_id: str) -> Optional[bool]:
        """``players[].goal_locked`` を検証する (目的層 G6)。

        None (未指定) はシナリオ全体の性質から導出する意味なので、False とは
        区別して保持する。bool 以外は誤記として弾く — 0 / 1 / "true" を暗黙に
        受けると「locked のつもりが unlocked」の取り違えが静かに通るため。
        """
        if raw is None:
            return None
        if not isinstance(raw, bool):
            raise ValueError(
                f"player '{owner_id}': goal_locked must be a boolean, "
                f"got {type(raw).__name__}"
            )
        return raw

    @staticmethod
    def _parse_player_initial_state(
        raw: Any, *, owner_id: str,
    ) -> Dict[str, Any]:
        """`players[].initial_state` を JSON プリミティブの flat dict に正規化。

        `PlayerStatusAggregate.state` の制約 (str / int / float / bool / None) に
        合わない値はシナリオ load 時点で `ScenarioLoadError` として弾く。
        domain 層側でも `PlayerStateValidationException` として再検証されるが、
        load 時点で落とせば「実行直前まで気付かない」事故が減る。
        """
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_state must be an object "
                f"(got {type(raw).__name__})"
            )
        allowed = (str, int, float, bool, type(None))
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_state key must be string "
                    f"(got {type(key).__name__}: {key!r})"
                )
            if not isinstance(value, allowed):
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_state[{key!r}] must be a JSON primitive "
                    f"(str / int / float / bool / null), got {type(value).__name__}"
                )
        return dict(raw)

    def _parse_initial_item(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
        *,
        owner_id: str,
    ) -> InitialItemSpec:
        """`initial_items` の 1 要素を `InitialItemSpec` にパース。

        受け付ける形式は 2 つ:
          - `"spec_string_id"` (state なし、Phase 4-A 以前のシナリオと互換)
          - `{"spec": "spec_string_id", "state": {...}}` (state を仕込める Phase 4-D 形式)
        どちらも 1 つの InitialItemSpec に正規化される。
        """
        if isinstance(raw, str):
            spec_id = ItemSpecId.create(mapper.get_int("item_spec", raw))
            return InitialItemSpec(spec_id=spec_id, state={})
        if isinstance(raw, dict):
            spec_string = raw.get("spec")
            if not isinstance(spec_string, str) or not spec_string:
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_items[*].spec is required "
                    f"(got {spec_string!r})"
                )
            spec_id = ItemSpecId.create(mapper.get_int("item_spec", spec_string))
            state_raw = raw.get("state", {})
            if not isinstance(state_raw, dict):
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_items[*].state must be an object "
                    f"(got {type(state_raw).__name__})"
                )
            return InitialItemSpec(spec_id=spec_id, state=dict(state_raw))
        raise ScenarioLoadError(
            f"players[{owner_id}].initial_items[*] must be a string or object "
            f"(got {type(raw).__name__})"
        )

    @staticmethod
    def _parse_needs_config(raw: Any) -> ScenarioNeedsConfig:
        """needs 機構の調整値を読み、無宣言なら飢餓ダメージを無効にする。"""
        if raw is None:
            return ScenarioNeedsConfig()
        if not isinstance(raw, dict):
            raise ScenarioLoadError("needs must be an object")
        starvation_damage = raw.get("starvation_damage_per_tick", 0)
        if (
            isinstance(starvation_damage, bool)
            or not isinstance(starvation_damage, int)
            or starvation_damage < 0
        ):
            raise ScenarioLoadError(
                "needs.starvation_damage_per_tick must be a non-negative integer"
            )
        return ScenarioNeedsConfig(
            starvation_damage_per_tick=starvation_damage,
        )

    def _parse_disabled_tools(self, raw: Any) -> Tuple[str, ...]:
        """``disabled_tools`` を読む。

        ここでは形だけを見る。**名前が実在するかは runtime 側で確かめる。**
        ツール名の一覧は application 層にあり、infrastructure から参照すると
        依存が逆向きになる。実在しない名前を書いても黙って無視されると
        「無効化したつもりが出たまま」になるので、起動時に落とす
        (``ToolExposureConfigurationError``)。

        重複はエラーにする。同じ名前が 2 度書かれているのは、多くの場合
        片方が消し忘れか書き換え漏れで、意図が読めない。
        """
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ScenarioLoadError("disabled_tools はリストで書いてください")
        names: list[str] = []
        for entry in raw:
            if not isinstance(entry, str) or not entry.strip():
                raise ScenarioLoadError(
                    f"disabled_tools の要素は空でない文字列にしてください: {entry!r}"
                )
            name = entry.strip()
            if name in names:
                raise ScenarioLoadError(f"disabled_tools に重複があります: {name}")
            names.append(name)
        return tuple(names)

    def _parse_end_conditions(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
        *,
        section: str,
    ) -> List[GameEndCondition]:
        if not raw:
            return []
        items = raw if isinstance(raw, list) else [raw]
        conditions: List[GameEndCondition] = []
        for index, item in enumerate(items):
            ctype = GameEndConditionTypeEnum[item["type"]]
            allowed_sections = _GAME_END_CONDITION_ALLOWED_SECTIONS.get(ctype)
            if allowed_sections is None:
                raise ScenarioLoadError(
                    f"game_end_conditions の条件型 {ctype.value} は置き場所が"
                    "未分類です"
                )
            if section not in allowed_sections:
                allowed = " / ".join(
                    name for name in ("win", "lose", "end")
                    if name in allowed_sections
                )
                raise ScenarioLoadError(
                    f"game_end_conditions.{section} に {ctype.value} は置けません。"
                    f"{allowed} に置いてください [index={index}]"
                )
            self._validate_end_condition_required_fields(item, ctype, index=index)
            target_spot = None
            if "target_spot" in item:
                target_spot = SpotId.create(mapper.get_int("spot", item["target_spot"]))
            conditions.append(GameEndCondition(
                condition_type=ctype,
                target_spot_id=target_spot,
                target_flag=item.get("target_flag"),
                tick_limit=item.get("tick_limit"),
                required_state=item.get("required_state"),
                max_surviving=item.get("max_surviving"),
                comparison_state=item.get("comparison_state"),
                required_flags=(
                    tuple(item["required_flags"])
                    if isinstance(item.get("required_flags"), list)
                    else None
                ),
                min_set_count=item.get("min_set_count"),
            ))
        return conditions

    def _validate_end_condition_required_fields(
        self,
        item: Dict[str, Any],
        ctype: GameEndConditionTypeEnum,
        *,
        index: int,
    ) -> None:
        """game_end_conditions の条件型ごとの必須フィールドをロード時に検査する。"""
        if ctype is GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST:
            required_flags = item.get("required_flags")
            if not isinstance(required_flags, list) or not required_flags:
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} には required_flags の"
                    "配列が必要です (空だと開始した瞬間に成立します)"
                    f" [index={index}]"
                )
            if not all(
                isinstance(name, str) and name.strip() for name in required_flags
            ):
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} の required_flags は"
                    "空でない文字列の配列である必要があります"
                    f" [index={index}]"
                )
            min_set_count = item.get("min_set_count")
            if not isinstance(min_set_count, int) or isinstance(min_set_count, bool):
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} には整数の min_set_count"
                    "が必要です (既定を『全部』にすると書き忘れと区別できません)"
                    f" [index={index}]"
                )
            # 数の整合 (0 以下 / 上限超え / 重複) は GameEndCondition の
            # __post_init__ が見る。ここで二重に書くと判断が 2 箇所に散る。
            return

        if ctype == GameEndConditionTypeEnum.FLAG_SET:
            target_flag = item.get("target_flag")
            if not isinstance(target_flag, str) or not target_flag.strip():
                raise ScenarioLoadError(
                    "game_end_conditions の FLAG_SET には target_flag が必要です "
                    "(scenario_events の FLAG_SET は flag_name ですが、"
                    "こちらは target_flag です)"
                    f" [index={index}]"
                )
            return
        if ctype == GameEndConditionTypeEnum.TICK_LIMIT:
            if item.get("tick_limit") is None:
                raise ScenarioLoadError(
                    "game_end_conditions の TICK_LIMIT には tick_limit が必要です"
                    f" [index={index}]"
                )
            return
        if ctype is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST:
            required_state = item.get("required_state")
            if not isinstance(required_state, dict) or not required_state:
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} には required_state が"
                    "必要です (誰を数えるかが決まりません)"
                    f" [index={index}]"
                )
            max_surviving = item.get("max_surviving")
            if not isinstance(max_surviving, int) or isinstance(max_surviving, bool):
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} には整数の max_surviving が"
                    "必要です (0 を既定にすると書き忘れと全滅指定を区別できません)"
                    f" [index={index}]"
                )
            if max_surviving < 0:
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} の max_surviving は 0 以上"
                    f"である必要があります: {max_surviving} [index={index}]"
                )
            return
        if (
            ctype
            is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE
        ):
            for field_name in ("required_state", "comparison_state"):
                state = item.get(field_name)
                if not isinstance(state, dict) or not state:
                    raise ScenarioLoadError(
                        f"game_end_conditions の {ctype.value} には {field_name} が"
                        f"必要です [index={index}]"
                    )
            # 左右が同じ集合かは GameEndCondition が単一の判断場所として見る。
            return
        if ctype in (
            GameEndConditionTypeEnum.ALL_AT_SPOT,
            GameEndConditionTypeEnum.ANY_AT_SPOT,
        ):
            target_spot = item.get("target_spot")
            if not isinstance(target_spot, str) or not target_spot.strip():
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} には target_spot が必要です"
                    f" [index={index}]"
                )
