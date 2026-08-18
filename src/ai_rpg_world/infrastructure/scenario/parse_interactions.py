"""interaction 定義と cooldown / notify の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    ITEM_ACTION_NAME_PREFIX,
    RESERVED_ACTION_NAME_PREFIX,
)
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import InteractionActorPlane
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import InteractionCooldownScope
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import parse_bool
from ai_rpg_world.infrastructure.scenario.parse_interaction_conditions import (
    parse_interaction_condition,
)
from ai_rpg_world.infrastructure.scenario.parse_interaction_effects import (
    parse_interaction_effect,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def parse_interaction_def(
    raw: Dict[str, Any],
    mapper: ScenarioIdMapper,
    *,
    allow_target_notification: bool = False,
    player_attribute_specs: PlayerAttributeSpecs,
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
        parse_interaction_effect(
            e, mapper, player_attribute_specs=player_attribute_specs
        )
        for e in raw.get("effects", [])
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

def parse_player_interactions(
    raw_list: Any,
    mapper: ScenarioIdMapper,
    *,
    player_attribute_specs: PlayerAttributeSpecs,
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
            raw,
            mapper,
            allow_target_notification=True,
            player_attribute_specs=player_attribute_specs,
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
