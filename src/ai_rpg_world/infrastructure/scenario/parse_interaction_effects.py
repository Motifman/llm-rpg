"""interaction 効果の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Set, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    CALL_MEETING_EFFECT_TRIGGERS,
    InteractionEffect,
)
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

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

#: 行為者本人の自由 state を書く効果と、書き先の key の読み方。
#:
#: `acting_player_status.merge_state` を呼ぶ handler を grep して数えた
#: (`handlers/player_state.py` の 2 件)。効果を増やすときは、あちらと対で見る。
_PLAYER_STATE_WRITERS = {
    InteractionEffectTypeEnum.CHANGE_PLAYER_STATE.name: "state_updates",
    InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK.name: "state_key",
}


def _written_player_state_keys(
    effect_type_str: str, params: Mapping[str, Any]
) -> Tuple[str, ...]:
    """その効果が書き換える、本人 state の key を返す。"""
    source = _PLAYER_STATE_WRITERS.get(effect_type_str)
    if source is None:
        return ()
    if source == "state_key":
        key = params.get("state_key")
        return (str(key),) if isinstance(key, str) and key else ()
    updates = params.get("state_updates")
    return tuple(str(k) for k in updates) if isinstance(updates, dict) else ()


def _reject_writes_to_unchangeable_attributes(
    effect_type_str: str,
    params: Mapping[str, Any],
    specs: PlayerAttributeSpecs,
) -> None:
    """変えられないと宣言した属性を書く効果を、読み込み時に落とす。

    **書けてしまう状態は、宣言しないより悪い。** 「変えられない」と読んで
    諦めた行為が別の宣言では成立するなら、世界の規則が場所によって違う
    ことになる。

    落とすのは**宣言が有る属性だけ**。宣言の無い属性は従来どおり書ける。

    ``RECORD_PLAYER_STATE_TICK`` も対象にする。書き込むのは tick の数値
    なので、``CHANGE_PLAYER_STATE`` より**壊れ方が分かりにくい** (``state_key``
    に生業を指定すれば、生業が数値で上書きされる)。
    """
    for key in _written_player_state_keys(effect_type_str, params):
        spec = specs.spec_of(key)
        if spec is None or spec.mutable:
            continue
        raise ScenarioLoadError(
            f"{effect_type_str} が、変えられないと宣言された属性 "
            f"'{key}' ({spec.display_name}) を書こうとしています。"
            f"player_attributes.{key}.mutable を true にするか、"
            f"この効果をやめてください"
        )


def parse_interaction_effect(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    actor_context: str = "interaction",
    player_attribute_specs: PlayerAttributeSpecs,
) -> InteractionEffect:
    """効果 1 件をパースする。

    ``actor_context`` は「この効果が誰の行為として適用されるか」を表す。
    ``interaction`` 以外 (scenario_event / synchronized_action_group) には
    行為者が存在せず、``target=TARGET_PLAYER`` を書いても誰を対象にするか
    決まらない。書けるのに何も起きない状態を残さないため、その文脈では
    読み込み時に落とす。

    ``player_attribute_specs`` は「**変えられないと宣言した属性を書く効果**」
    を落とすために使う。

    **省略可能にしていない。** 既定を「宣言なし」にすると、新しい入口が
    渡し忘れた瞬間に**その入口だけ検査が消える**。しかも消えたことは緑の
    まま進む。必須なら、渡さない限り呼べない。
    """
    params = dict(raw.get("parameters", {}))
    effect_type_str = raw.get("effect_type", "")
    _reject_writes_to_unchangeable_attributes(
        effect_type_str, params, player_attribute_specs
    )
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
