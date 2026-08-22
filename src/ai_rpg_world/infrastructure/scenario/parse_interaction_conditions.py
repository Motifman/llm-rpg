"""interaction 条件の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ai_rpg_world.infrastructure.scenario.validate_attribute_values import (
    reject_values_the_world_does_not_have,
)
from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    parse_hp_ratio,
    parse_item_spec_id_parameter_key,
    parse_need_type,
    parse_required_quantity,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def parse_interaction_condition(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    player_attribute_specs: PlayerAttributeSpecs,
) -> InteractionCondition:
    if raw.get("condition_type") in (
        "PLAYER_STATE_IS", "TARGET_PLAYER_STATE_IS",
    ):
        reject_values_the_world_does_not_have(
            raw.get("required_state") or {},
            player_attribute_specs,
            what=f"{raw.get('condition_type')}.required_state",
        )
    item_sid = raw.get("required_item")
    item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
    obj_sid = raw.get("target_object")
    obj_id = SpotObjectId.create(mapper.get_int("object", obj_sid)) if obj_sid else None
    # 対象所持条件は、判定する品目の出所が要る。どちらも無いと条件は
    # 永久に不成立になり、interaction が黙って使えなくなる。実 run で
    # 「なぜか一度も成功しない」として初めて気付くことになるので、
    # 読み込み時に落とす。
    parameter_key = parse_item_spec_id_parameter_key(raw)
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
    required_lighting = parse_required_lighting(raw)
    required_spot_id = parse_required_spot_id(raw, mapper)
    if raw.get("condition_type") == "PLAYER_GOLD_AT_LEAST":
        gold_threshold = raw.get("gold_threshold")
        if not isinstance(gold_threshold, int) or gold_threshold <= 0:
            raise ScenarioLoadError(
                "PLAYER_GOLD_AT_LEAST requires a positive int gold_threshold; "
                f"無いと条件は常に不成立になります: {raw!r}"
            )
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
        required_quantity=parse_required_quantity(raw),
        state_key=(
            raw.get("state_key", "").strip()
            if isinstance(raw.get("state_key"), str)
            else raw.get("state_key")
        ),
        need_type=parse_need_type(raw),
        need_threshold=raw.get("need_threshold"),
        gold_threshold=raw.get("gold_threshold"),
        hp_ratio=parse_hp_ratio(raw),
        # PR4: TIME_OF_DAY_IS{_NOT} / WEATHER_IS{_NOT} 用フィールド。
        # phase / weather_type は単純な文字列で受け取り、ランタイムで
        # 現在値と比較する。boundary 検証は別 PR で (現状 day_night の
        # phase 名はシナリオ宣言依存のため固定値リストを持たない)。
        required_time_of_day_phase=raw.get("required_time_of_day_phase"),
        required_weather_type=parse_required_weather_type(raw),
        # 対人 interaction: TARGET_HAS_ITEM / TARGET_HAS_NO_ITEM が判定
        # する品目を、interaction_parameters のどのキーから取るか。
        item_spec_id_parameter_key=parameter_key,
        # PR 3: 場所条件。SPOT_LIGHTING_IS{_NOT} / AT_SPOT_IS{_NOT} 用。
        required_lighting=required_lighting,
        required_spot_id=required_spot_id,
    )

_LIGHTING_CONDITIONS = ("SPOT_LIGHTING_IS", "SPOT_LIGHTING_IS_NOT")

_AT_SPOT_CONDITIONS = ("AT_SPOT_IS", "AT_SPOT_IS_NOT")

def parse_required_lighting( raw: Dict[str, Any]) -> Optional[str]:
    """``required_lighting`` を検証して返す。

    値は ``LightingEnum`` のメンバ名に限る。タイポを実行時まで持ち越すと
    「照明が一致しないので不成立」と区別がつかず、シナリオ作者が書いた
    failure_message の裏にタイポが隠れる。
    """
    condition_type = raw.get("condition_type")
    value = raw.get("required_lighting")
    if value is None:
        if condition_type in _LIGHTING_CONDITIONS:
            raise ScenarioLoadError(
                f"{condition_type} requires required_lighting; "
                f"無いと条件は常に不成立になります: {raw!r}"
            )
        return None
    if condition_type not in _LIGHTING_CONDITIONS:
        raise ScenarioLoadError(
            f"required_lighting is only valid on {_LIGHTING_CONDITIONS}, "
            f"got condition_type={condition_type!r}: {raw!r}"
        )
    valid = tuple(level.value for level in LightingEnum)
    if value not in valid:
        raise ScenarioLoadError(
            f"required_lighting must be one of {valid}, got {value!r}: {raw!r}"
        )
    return value

_WEATHER_CONDITIONS = ("WEATHER_IS", "WEATHER_IS_NOT")

def parse_required_weather_type( raw: Dict[str, Any]) -> Optional[str]:
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
        if condition_type in _WEATHER_CONDITIONS:
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

def parse_required_spot_id( raw: Dict[str, Any], mapper: ScenarioIdMapper
) -> Optional[SpotId]:
    """``required_spot`` (シナリオ上の文字列 ID) を SpotId に解決する。"""
    condition_type = raw.get("condition_type")
    value = raw.get("required_spot")
    if value is None:
        if condition_type in _AT_SPOT_CONDITIONS:
            raise ScenarioLoadError(
                f"{condition_type} requires required_spot; "
                f"無いと条件は常に不成立になります: {raw!r}"
            )
        return None
    if condition_type not in _AT_SPOT_CONDITIONS:
        raise ScenarioLoadError(
            f"required_spot is only valid on {_AT_SPOT_CONDITIONS}, "
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
