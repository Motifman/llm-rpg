"""シナリオ機能の整合性検査。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ai_rpg_world.application.llm.tool_exposure import ToolExposure
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.models import ScenarioLoadResult
from ai_rpg_world.infrastructure.scenario.parse_helpers import iter_mappings

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
    InteractionConditionTypeEnum.PLAYER_GOLD_AT_LEAST: None,
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

def validate_feature_consistency(
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

    nodes = tuple(iter_mappings(raw))
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

