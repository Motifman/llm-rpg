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


def apply_change_player_state(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    p = effect.parameters
    updates = p.get("state_updates")
    if not isinstance(updates, dict):
        _logger.warning(
            "CHANGE_PLAYER_STATE: parameters.state_updates must be dict (got %s)",
            type(updates).__name__,
        )
        return
    if ctx.acting_player_status is None:
        _logger.warning(
            "CHANGE_PLAYER_STATE: caller did not provide acting_player_status; "
            "skipping state merge"
        )
        return
    before_state = dict(ctx.acting_player_status.state)
    ctx.acting_player_status.merge_state(updates)
    after_state = dict(ctx.acting_player_status.state)
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.ACTING_PLAYER_STATE_CHANGE,
            visibility=visibility,
            description="プレイヤー自身の状態が変化した",
            state_delta=state_delta_entries(before_state, after_state),
        )
    )


def apply_record_player_state_tick(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    state_key = p.get("state_key")
    if not isinstance(state_key, str) or not state_key:
        _logger.warning(
            "RECORD_PLAYER_STATE_TICK: state_key is required (got %r)",
            state_key,
        )
        return
    if ctx.current_tick is None:
        _logger.warning(
            "RECORD_PLAYER_STATE_TICK: caller did not provide current_tick; "
            "skipping write to state[%r]",
            state_key,
        )
        return
    if ctx.acting_player_status is None:
        _logger.warning(
            "RECORD_PLAYER_STATE_TICK: caller did not provide "
            "acting_player_status; skipping write to state[%r]",
            state_key,
        )
        return
    ctx.acting_player_status.merge_state({state_key: int(ctx.current_tick.value)})


def build_player_state_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.CHANGE_PLAYER_STATE: apply_change_player_state,
        InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK: apply_record_player_state_tick,
    }
