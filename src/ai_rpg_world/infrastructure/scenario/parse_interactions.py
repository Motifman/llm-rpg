"""interaction 定義・条件・効果の読み取り。"""

from __future__ import annotations

import logging
from string import Formatter
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    ITEM_ACTION_NAME_PREFIX,
    RESERVED_ACTION_NAME_PREFIX,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import InteractionActorPlane
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import InteractionCooldownScope
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    CALL_MEETING_EFFECT_TRIGGERS,
    InteractionEffect,
)
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    parse_bool,
    parse_hp_ratio,
    parse_item_spec_id_parameter_key,
    parse_need_type,
    parse_required_quantity,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def parse_interaction_def(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    allow_target_notification: bool = False,
) -> InteractionDef:
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
        parse_interaction_condition(c, mapper)
        for c in raw.get("preconditions", [])
    )
    effects = tuple(
        parse_interaction_effect(e, mapper) for e in raw.get("effects", [])
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
    notify_target, target_observation_message = parse_target_notification(
        raw, allow_target_notification=allow_target_notification
    )
    cooldown_ticks = parse_cooldown_ticks(raw)
    cooldown_group = parse_cooldown_group(raw)
    cooldown_scope = parse_cooldown_scope(raw)
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
    hide_when_flag_preconditions_fail = parse_bool(
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

def parse_cooldown_group(raw: Any) -> Optional[str]:
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

def parse_cooldown_ticks(raw: Any) -> int:
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

def parse_cooldown_scope(raw: Any) -> InteractionCooldownScope:
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

def parse_target_notification(
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

def parse_interaction_condition( raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionCondition:
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

_TARGET_PLAYER_CAPABLE_EFFECTS = frozenset(
    {
        InteractionEffectTypeEnum.GIVE_ITEM,
        InteractionEffectTypeEnum.REMOVE_ITEM,
        InteractionEffectTypeEnum.APPLY_DAMAGE,
    }
)

_TARGET_PLAYER_NOT_WIRED_YET = frozenset(
    {
        InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
        InteractionEffectTypeEnum.SATISFY_NEED,
        InteractionEffectTypeEnum.TELEPORT_ENTITY,
        InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
        InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
    }
)

def parse_effect_target( raw: Dict[str, Any], *, actor_context: str
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
    if effect_type in _TARGET_PLAYER_NOT_WIRED_YET:
        raise ScenarioLoadError(
            f"{effect_type.name} with target=TARGET_PLAYER is declared but not "
            "wired yet; 宣言しても対象ではなく行為者に効いてしまうため、"
            "配線が済むまで受け付けません: "
            f"{raw!r}"
        )
    if effect_type not in _TARGET_PLAYER_CAPABLE_EFFECTS:
        capable = ", ".join(
            sorted(e.name for e in _TARGET_PLAYER_CAPABLE_EFFECTS)
        )
        raise ScenarioLoadError(
            f"{effect_type.name} does not support target=TARGET_PLAYER. "
            f"対象を取れる効果: {capable}: {raw!r}"
        )
    return target

def parse_interaction_effect(
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
    target = parse_effect_target(raw, actor_context=actor_context)
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
        validate_teleport_observation_messages(params, raw)
    # CHANGE_ATMOSPHERE も同型の静かな失敗を持つ。対象 spot が無いと domain 側
    # は spec を作らず、enum 名の綴りを間違えても実行時まで気づけない。
    if effect_type is InteractionEffectTypeEnum.CHANGE_ATMOSPHERE:
        validate_change_atmosphere_params(params, raw)
    return InteractionEffect(
        effect_type=effect_type,
        parameters=params,
        visibility=visibility,
        target=target,
    )

_TELEPORT_PARAM_KEYS = frozenset(
    {
        "spot_id",
        "departure_observation_message",
        "departure_observation_message_in_dark",
        "arrival_observation_message",
        "arrival_observation_message_in_dark",
    }
)

_TELEPORT_MESSAGE_PLACEHOLDERS = frozenset({"{actor}"})

def validate_teleport_observation_messages( params: Dict[str, Any], raw: Dict[str, Any]
) -> None:
    """観測文の宣言ミスを起動時に落とす。

    **静かに既定文へ縮退する経路を塞ぐ。** 綴り違いの鍵は誰も読まず、
    非文字列は None へ落ち、未知のプレースホルダは展開されないまま出る。
    どれも「書いたのに効かない」形で、対象 spot の欠落を落としているのと
    同じ理由でここで止める。

    空文字も拒否する。formatter は空文字を「宣言なし」として既定文へ戻すので、
    「宣言したが空」を運ぶことはできない。**意味を一方へ揃える。**
    """
    unknown = sorted(set(params) - _TELEPORT_PARAM_KEYS)
    if unknown:
        raise ScenarioLoadError(
            f"TELEPORT_ENTITY effect has unknown parameters {unknown}. "
            f"書ける鍵は {sorted(_TELEPORT_PARAM_KEYS)} です "
            f"(綴り違いは黙って無視され、既定文へ縮退します): {raw!r}"
        )
    for key in _TELEPORT_PARAM_KEYS - {"spot_id"}:
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
            for known in _TELEPORT_MESSAGE_PLACEHOLDERS:
                remainder = remainder.replace(known, "")
            if "{" in remainder or "}" in remainder:
                raise ScenarioLoadError(
                    f"TELEPORT_ENTITY effect parameter '{key}' has a brace that "
                    f"is not a known placeholder ({value!r})。展開されるのは "
                    f"{sorted(_TELEPORT_MESSAGE_PLACEHOLDERS)} だけで、"
                    f"閉じ忘れや綴り違いはそのまま観測へ出ます: {raw!r}"
                )

def validate_change_atmosphere_params(
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

