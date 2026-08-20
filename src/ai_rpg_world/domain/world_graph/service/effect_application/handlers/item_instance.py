from __future__ import annotations

import logging

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    EffectHandlerFn,
)
from ai_rpg_world.domain.world_graph.service.effect_application.visibility import (
    resolve_visibility,
    state_delta_entries,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    AppliedEffectSummary,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)

_logger = logging.getLogger(__name__)


def apply_change_item_instance_state(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    updates = p.get("state_updates")
    if not isinstance(updates, dict):
        _logger.warning(
            "CHANGE_ITEM_INSTANCE_STATE: parameters.state_updates must be dict (got %s)",
            type(updates).__name__,
        )
        return
    if ctx.acting_item_aggregate is None:
        _logger.warning(
            "CHANGE_ITEM_INSTANCE_STATE: caller did not provide acting_item_aggregate; "
            "skipping state merge"
        )
        return
    before_state = dict(ctx.acting_item_aggregate.state)
    ctx.acting_item_aggregate.merge_state(updates)
    after_state = dict(ctx.acting_item_aggregate.state)
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.ACTING_ITEM_STATE_CHANGE,
            visibility=visibility,
            description="使ったアイテムの状態が変化した",
            target_ref=str(ctx.acting_item_aggregate.item_spec.item_spec_id.value),
            state_delta=state_delta_entries(before_state, after_state),
        )
    )


def apply_record_item_instance_state_tick(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    state_key = p.get("state_key")
    if not isinstance(state_key, str) or not state_key:
        _logger.warning(
            "RECORD_ITEM_INSTANCE_STATE_TICK: state_key is required (got %r)",
            state_key,
        )
        return
    if ctx.current_tick is None:
        _logger.warning(
            "RECORD_ITEM_INSTANCE_STATE_TICK: caller did not provide current_tick; "
            "skipping write to state[%r]",
            state_key,
        )
        return
    if ctx.acting_item_aggregate is None:
        _logger.warning(
            "RECORD_ITEM_INSTANCE_STATE_TICK: caller did not provide "
            "acting_item_aggregate; skipping write to state[%r]",
            state_key,
        )
        return
    ctx.acting_item_aggregate.merge_state({state_key: int(ctx.current_tick.value)})


def apply_change_target_item_instance_state(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    updates = p.get("state_updates")
    if not isinstance(updates, dict):
        _logger.warning(
            "CHANGE_TARGET_ITEM_INSTANCE_STATE: parameters.state_updates must be dict (got %s)",
            type(updates).__name__,
        )
        return
    if ctx.target_item_aggregate is None:
        _logger.warning(
            "CHANGE_TARGET_ITEM_INSTANCE_STATE: caller did not provide target_item_aggregate; "
            "skipping state merge"
        )
        return
    before_state = dict(ctx.target_item_aggregate.state)
    ctx.target_item_aggregate.merge_state(updates)
    after_state = dict(ctx.target_item_aggregate.state)
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.TARGET_ITEM_STATE_CHANGE,
            visibility=visibility,
            description="作用したアイテムの状態が変化した",
            target_ref=str(ctx.target_item_aggregate.item_spec.item_spec_id.value),
            state_delta=state_delta_entries(before_state, after_state),
        )
    )


def apply_record_target_item_instance_state_tick(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    state_key = p.get("state_key")
    if not isinstance(state_key, str) or not state_key:
        _logger.warning(
            "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: state_key is required (got %r)",
            state_key,
        )
        return
    if ctx.current_tick is None:
        _logger.warning(
            "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: caller did not provide current_tick; "
            "skipping write to state[%r]",
            state_key,
        )
        return
    if ctx.target_item_aggregate is None:
        _logger.warning(
            "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: caller did not provide "
            "target_item_aggregate; skipping write to state[%r]",
            state_key,
        )
        return
    ctx.target_item_aggregate.merge_state({state_key: int(ctx.current_tick.value)})


def build_item_instance_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE: apply_change_item_instance_state,
        InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK: apply_record_item_instance_state_tick,
        InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE: apply_change_target_item_instance_state,
        InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: apply_record_target_item_instance_state_tick,
    }
