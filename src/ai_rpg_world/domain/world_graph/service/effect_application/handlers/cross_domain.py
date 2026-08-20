from __future__ import annotations

import logging
from typing import Optional

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.item_transfer import (
    damage_bucket_for,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    EffectHandlerFn,
)
from ai_rpg_world.domain.world_graph.service.effect_application.visibility import (
    resolve_visibility,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    AppliedEffectSummary,
)
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    AtmosphereUpdateSpec,
    CreateConnectionSpec,
    DamageSpec,
    DestroyConnectionSpec,
    PassageStateUpdateSpec,
    SatisfyNeedSpec,
    StatusEffectSpec,
    TeleportSpec,
)
from ai_rpg_world.domain.world_graph.value_object import interaction_effect
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage

_logger = logging.getLogger(__name__)


def apply_call_meeting(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    trigger = effect.parameters.get("trigger")
    if trigger not in interaction_effect.CALL_MEETING_EFFECT_TRIGGERS:
        raise InteractionEffectValidationException(
            "CALL_MEETING requires a supported parameters.trigger: "
            f"allowed={sorted(interaction_effect.CALL_MEETING_EFFECT_TRIGGERS)!r}, "
            f"got={trigger!r}"
        )
    ctx.meeting_calls.append(trigger)


def apply_apply_damage(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    damage_val = int(p.get("damage", 0))
    msg = str(p.get("message", ""))
    if damage_val > 0:
        dmg_bucket = damage_bucket_for(
            effect,
            actor_bucket=ctx.damage_specs,
            target_bucket=ctx.target_damage_specs,
            target_player_status=ctx.target_player_status,
        )
        dmg_bucket.append(
            DamageSpec(damage=damage_val, message=msg, visibility=visibility)
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.DAMAGE,
                visibility=visibility,
                description=msg or f"{damage_val} のダメージを受けた",
            )
        )


def apply_apply_status_effect(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    effect_type_name = str(p.get("status_effect_type", ""))
    value = float(p.get("value", 1.0))
    duration_ticks = int(p.get("duration_ticks", 0))
    if effect_type_name and duration_ticks > 0:
        ctx.status_effect_specs.append(
            StatusEffectSpec(
                effect_type_name=effect_type_name,
                value=value,
                duration_ticks=duration_ticks,
                visibility=visibility,
            )
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.STATUS_EFFECT,
                visibility=visibility,
                description=(
                    f"{effect_type_name} の状態異常 (値={value}, {duration_ticks} ticks)"
                ),
                target_ref=effect_type_name,
            )
        )


def apply_teleport_entity(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    target_spot_id = int(p.get("spot_id", 0))
    if target_spot_id > 0:

        def _declared(key: str) -> Optional[str]:
            value = p.get(key)
            return value if isinstance(value, str) else None

        ctx.teleport_specs.append(
            TeleportSpec(
                target_spot_id=target_spot_id,
                visibility=visibility,
                departure_observation_message=_declared(
                    "departure_observation_message"
                ),
                departure_observation_message_in_dark=_declared(
                    "departure_observation_message_in_dark"
                ),
                arrival_observation_message=_declared("arrival_observation_message"),
                arrival_observation_message_in_dark=_declared(
                    "arrival_observation_message_in_dark"
                ),
            )
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.TELEPORT,
                visibility=visibility,
                description=f"スポット {target_spot_id} へ転移した",
                target_ref=str(target_spot_id),
            )
        )


def apply_change_atmosphere(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    spot_id = int(p.get("spot_id", 0))
    if spot_id > 0:
        ctx.atmosphere_update_specs.append(
            AtmosphereUpdateSpec(
                spot_id=spot_id,
                lighting=p.get("lighting"),
                temperature=p.get("temperature"),
                hazard_level=p.get("hazard_level"),
                hazard_description=p.get("hazard_description"),
                visibility=visibility,
            )
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.ATMOSPHERE_UPDATE,
                visibility=visibility,
                description=f"スポット {spot_id} の雰囲気が変化した",
                target_ref=str(spot_id),
            )
        )


def apply_create_connection(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    from_sid = int(p.get("from_spot_id", 0))
    to_sid = int(p.get("to_spot_id", 0))
    conn_name = str(p.get("connection_name", ""))
    if from_sid > 0 and to_sid > 0 and conn_name:
        if "passage" not in p:
            _logger.warning(
                "CREATE_CONNECTION effect for '%s' is missing 'passage' "
                "block; defaulting to Passage.open()",
                conn_name,
            )
        ctx.create_connection_specs.append(
            CreateConnectionSpec(
                from_spot_id=from_sid,
                to_spot_id=to_sid,
                connection_name=conn_name,
                description=str(p.get("description", "")),
                travel_ticks=int(p.get("travel_ticks", 1)),
                is_bidirectional=bool(p.get("is_bidirectional", False)),
                passage=Passage.from_dict(p.get("passage")),
                visibility=visibility,
            )
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.CONNECTION_CREATED,
                visibility=visibility,
                description=(
                    f"スポット {from_sid} と {to_sid} を結ぶ接続「{conn_name}」が現れた"
                ),
                target_ref=conn_name,
            )
        )


def apply_destroy_connection(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    cid = int(p.get("connection_id", 0))
    if cid > 0:
        ctx.destroy_connection_specs.append(
            DestroyConnectionSpec(connection_id=cid, visibility=visibility)
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.CONNECTION_DESTROYED,
                visibility=visibility,
                description=f"接続 {cid} が消滅した",
                target_ref=str(cid),
            )
        )


def apply_satisfy_need(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    need_type_name = str(p.get("need_type", ""))
    amount = int(p.get("amount", 0))
    if need_type_name and amount > 0:
        ctx.satisfy_need_specs.append(
            SatisfyNeedSpec(
                need_type_name=need_type_name,
                amount=amount,
                visibility=visibility,
            )
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.SATISFY_NEED,
                visibility=visibility,
                description=f"{need_type_name} を {amount} 回復した",
                target_ref=need_type_name,
            )
        )


def apply_change_passage_state(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    cid_raw = p.get("connection_id")
    new_state = p.get("new_state")
    if cid_raw is not None and isinstance(new_state, str) and new_state:
        trav = p.get("traversable")
        sound = p.get("sound_permeability")
        ctx.passage_specs.append(
            PassageStateUpdateSpec(
                connection_id=int(cid_raw),
                new_state=new_state,
                traversable_override=bool(trav) if trav is not None else None,
                sound_permeability_override=float(sound) if sound is not None else None,
                visibility=visibility,
            )
        )
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.PASSAGE_STATE_UPDATE,
                visibility=visibility,
                description=f"接続 {int(cid_raw)} の通過状態が {new_state} に変化した",
                target_ref=str(int(cid_raw)),
            )
        )


def build_cross_domain_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.CALL_MEETING: apply_call_meeting,
        InteractionEffectTypeEnum.APPLY_DAMAGE: apply_apply_damage,
        InteractionEffectTypeEnum.APPLY_STATUS_EFFECT: apply_apply_status_effect,
        InteractionEffectTypeEnum.TELEPORT_ENTITY: apply_teleport_entity,
        InteractionEffectTypeEnum.CHANGE_ATMOSPHERE: apply_change_atmosphere,
        InteractionEffectTypeEnum.CREATE_CONNECTION: apply_create_connection,
        InteractionEffectTypeEnum.DESTROY_CONNECTION: apply_destroy_connection,
        InteractionEffectTypeEnum.SATISFY_NEED: apply_satisfy_need,
        InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE: apply_change_passage_state,
    }
