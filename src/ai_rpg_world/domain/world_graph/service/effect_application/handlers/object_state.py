from __future__ import annotations

import logging

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.object_target import (
    resolve_target_object,
    spot_object_id_from_param,
    sub_location_id_from_param,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    EffectHandlerFn,
)
from ai_rpg_world.domain.world_graph.service.effect_application.visibility import (
    resolve_visibility,
    state_delta_entries,
)
from ai_rpg_world.domain.world_graph.service.stock_pool_regen import (
    compute_stock_regen,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    AppliedEffectSummary,
)
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    DepositGoldSpec,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)

_logger = logging.getLogger(__name__)


def apply_increment_object_state(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    state_key = p.get("state_key")
    delta = int(p.get("delta", 1))
    if not isinstance(state_key, str) or not state_key:
        _logger.warning(
            "INCREMENT_OBJECT_STATE: state_key is required (got %r), "
            "skipping effect",
            state_key,
        )
        return
    target = resolve_target_object(ctx.interior, ctx.acting_object, p)
    if target is None:
        _logger.warning(
            "INCREMENT_OBJECT_STATE: target object not resolvable "
            "(state_key=%r, target_object=%r), skipping effect",
            state_key,
            p.get("target_object"),
        )
        return
    current = target.state.get(state_key, 0)
    if not isinstance(current, int):
        _logger.warning(
            "INCREMENT_OBJECT_STATE: target %r state[%r] is %r "
            "(non-int), resetting to 0 before increment",
            target.name,
            state_key,
            current,
        )
        current = 0
    new_value = current + delta
    new_state = dict(target.state)
    new_state[state_key] = new_value
    updated_target = target.with_state(new_state)
    before_state = dict(target.state)
    ctx.replace_object(updated_target)
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE,
            visibility=visibility,
            description=f"{updated_target.name} の {state_key} が {new_value} に。",
            target_ref=updated_target.name,
            state_delta=state_delta_entries(before_state, new_state),
        )
    )


def apply_deposit_gold_to_object(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    """行為者の gold を object.state の累積値へ移す。

    state 加算と支払い予約 (deposit_gold_specs) を 1 effect 内で同じ値から
    作り、別 effect の組合せによる金額ずれを防ぐ (DEPOSIT_ITEM_TO_OBJECT と
    同じ理由)。所持金の不足は前提条件 (PLAYER_GOLD_AT_LEAST) が読み込み時の
    ペア強制で先に受け止めるので、ここでは検査しない。
    """
    visibility = resolve_visibility(effect)
    p = effect.parameters
    state_key = p.get("state_key")
    amount = int(p.get("amount", 0))
    if not isinstance(state_key, str) or not state_key:
        _logger.warning(
            "DEPOSIT_GOLD_TO_OBJECT: state_key is required (got %r), "
            "skipping effect",
            state_key,
        )
        return
    if amount <= 0:
        _logger.warning(
            "DEPOSIT_GOLD_TO_OBJECT: amount must be positive (got %r), "
            "skipping effect",
            amount,
        )
        return
    target = resolve_target_object(ctx.interior, ctx.acting_object, p)
    if target is None:
        _logger.warning(
            "DEPOSIT_GOLD_TO_OBJECT: target object not resolvable "
            "(state_key=%r, target_object=%r), skipping effect",
            state_key,
            p.get("target_object"),
        )
        return
    current = target.state.get(state_key, 0)
    if not isinstance(current, int):
        current = 0
    new_state = dict(target.state)
    new_state[state_key] = current + amount
    before_state = dict(target.state)
    updated_target = target.with_state(new_state)
    ctx.replace_object(updated_target)
    ctx.deposit_gold_specs.append(DepositGoldSpec(amount=amount))
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE,
            visibility=visibility,
            description=f"{updated_target.name} へ {amount}G を納めた。",
            target_ref=updated_target.name,
            state_delta=state_delta_entries(before_state, new_state),
        )
    )


def apply_consume_object_stock(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    amount = max(0, int(p.get("amount", 1)))
    target = resolve_target_object(ctx.interior, ctx.acting_object, p)
    if target is None:
        _logger.warning(
            "CONSUME_OBJECT_STOCK: target object not resolvable "
            "(target_object=%r), skipping effect",
            p.get("target_object"),
        )
        return
    st = target.state
    now = (
        int(ctx.current_tick.value)
        if ctx.current_tick is not None
        else int(st.get("stock_tick", 0))
    )
    regen = compute_stock_regen(
        stock=int(st.get("stock", 0)),
        capacity=int(st.get("stock_capacity", 0)),
        stock_tick=int(st.get("stock_tick", 0)),
        refill_interval=int(st.get("stock_refill_interval", 0)),
        now=now,
    )
    new_stock = max(0, regen.effective_stock - amount)
    new_state = dict(target.state)
    new_state["stock"] = new_stock
    new_state["stock_tick"] = regen.canonical_tick
    before_state = dict(target.state)
    updated_target = target.with_state(new_state)
    ctx.replace_object(updated_target)
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE,
            visibility=visibility,
            description=f"{updated_target.name} の備蓄が {new_stock} に。",
            target_ref=updated_target.name,
            state_delta=state_delta_entries(before_state, new_state),
        )
    )


def apply_change_object_state(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    updates = p.get("state_updates")
    if isinstance(updates, dict):
        target = resolve_target_object(ctx.interior, ctx.acting_object, p)
        if target is None:
            return
        before_state = dict(target.state)
        new_state = dict(target.state)
        for k, v in updates.items():
            new_state[str(k)] = v
        updated_target = target.with_state(new_state)
        ctx.replace_object(updated_target)
        ctx.summaries.append(
            AppliedEffectSummary(
                kind=AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE,
                visibility=visibility,
                description=f"{updated_target.name} の状態が変化した",
                target_ref=updated_target.name,
                state_delta=state_delta_entries(before_state, new_state),
            )
        )


def apply_reveal_object(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    p = effect.parameters
    oid = spot_object_id_from_param(p.get("object_id"))
    target = ctx.interior.get_object(oid)
    if target is not None:
        revealed = target.with_visible(True)
        ctx.replace_object(revealed)


def apply_reveal_sub_location(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    slid = sub_location_id_from_param(p.get("sub_location_id"))
    for sl in ctx.interior.sub_locations:
        if sl.sub_location_id == slid:
            ctx.interior = ctx.interior.replace_sub_location(sl.revealed())
            break


def apply_record_object_state_tick(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    state_key = p.get("state_key")
    if not isinstance(state_key, str) or not state_key:
        _logger.warning(
            "RECORD_OBJECT_STATE_TICK: state_key is required (got %r)",
            state_key,
        )
        return
    if ctx.current_tick is None:
        _logger.warning(
            "RECORD_OBJECT_STATE_TICK: caller did not provide current_tick; "
            "skipping write to state[%r]",
            state_key,
        )
        return
    target = resolve_target_object(ctx.interior, ctx.acting_object, p)
    if target is None:
        return
    new_state = dict(target.state)
    new_state[state_key] = int(ctx.current_tick.value)
    updated_target = target.with_state(new_state).with_additional_hidden_state_keys(
        frozenset({state_key})
    )
    ctx.replace_object(updated_target)


def build_object_state_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE: apply_increment_object_state,
        InteractionEffectTypeEnum.DEPOSIT_GOLD_TO_OBJECT: apply_deposit_gold_to_object,
        InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK: apply_consume_object_stock,
        InteractionEffectTypeEnum.CHANGE_OBJECT_STATE: apply_change_object_state,
        InteractionEffectTypeEnum.REVEAL_OBJECT: apply_reveal_object,
        InteractionEffectTypeEnum.REVEAL_SUB_LOCATION: apply_reveal_sub_location,
        InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK: apply_record_object_state_tick,
    }
