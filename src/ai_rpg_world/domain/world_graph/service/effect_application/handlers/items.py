from __future__ import annotations

import logging

from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.item_transfer import (
    deposit_removal_details,
    item_bucket_for,
    item_removals_for_effect,
    item_spec_from_param,
    read_quantity,
    resolve_item_spec_for_transfer,
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


def apply_give_item(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    p = effect.parameters
    sid = resolve_item_spec_for_transfer(
        p, ctx.interaction_parameters, "GIVE_ITEM"
    )
    quantity = read_quantity(p)
    bucket = item_bucket_for(
        effect,
        actor_bucket=ctx.grant,
        target_bucket=ctx.target_grant,
        target_player_status=ctx.target_player_status,
    )
    for _ in range(quantity):
        bucket.append(sid)


def apply_give_from_loot_table(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    p = effect.parameters
    if ctx.loot_table_repository is None:
        _logger.warning(
            "GIVE_FROM_LOOT_TABLE: loot_table_repository is not injected, skipping"
        )
        return
    lt_id_raw = p.get("loot_table_id")
    try:
        lt_id_int = int(lt_id_raw)
    except (TypeError, ValueError):
        _logger.warning(
            "GIVE_FROM_LOOT_TABLE: loot_table_id is invalid (got %r)", lt_id_raw
        )
        return
    lt = ctx.loot_table_repository.find_by_id(LootTableId.create(lt_id_int))
    if lt is None:
        _logger.warning(
            "GIVE_FROM_LOOT_TABLE: loot_table_id=%s not found", lt_id_int
        )
        return
    times = max(1, min(100, int(p.get("times", 1))))
    for _ in range(times):
        rolled = lt.roll()
        if rolled is None:
            continue
        for _q in range(rolled.quantity):
            ctx.grant.append(rolled.item_spec_id)


def apply_remove_item(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    actor_items, target_items = item_removals_for_effect(
        interior=ctx.interior,
        acting_object=ctx.acting_object,
        effect=effect,
        interaction_parameters=ctx.interaction_parameters,
        owned_item_spec_counts=ctx.owned_item_spec_counts,
        target_player_status=ctx.target_player_status,
    )
    ctx.remove.extend(actor_items)
    ctx.target_remove.extend(target_items)


def apply_deposit_item_to_object(
    effect: InteractionEffect, ctx: EffectApplicationState
) -> None:
    visibility = resolve_visibility(effect)
    sid, state_key, target, deposited = deposit_removal_details(
        interior=ctx.interior,
        acting_object=ctx.acting_object,
        effect=effect,
        interaction_parameters=ctx.interaction_parameters,
        owned_item_spec_counts=ctx.owned_item_spec_counts,
    )
    if deposited == 0:
        return

    current = target.state.get(state_key, 0)
    if not isinstance(current, int):
        current = 0
    new_state = dict(target.state)
    new_state[state_key] = current + deposited
    updated_target = target.with_state(new_state)
    ctx.replace_object(updated_target)
    for _ in range(deposited):
        ctx.remove.append(sid)
    ctx.summaries.append(
        AppliedEffectSummary(
            kind=AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE,
            visibility=visibility,
            description=f"{updated_target.name} の {state_key} が変化した。",
            target_ref=updated_target.name,
            state_delta=state_delta_entries(target.state, new_state),
        )
    )


def apply_combine_items(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    p = effect.parameters
    actor_items, _target_items = item_removals_for_effect(
        interior=ctx.interior,
        acting_object=ctx.acting_object,
        effect=effect,
        interaction_parameters=ctx.interaction_parameters,
        owned_item_spec_counts=ctx.owned_item_spec_counts,
        target_player_status=ctx.target_player_status,
    )
    output_id = p.get("output_item_spec_id")
    ctx.remove.extend(actor_items)
    if output_id is not None:
        ctx.grant.append(item_spec_from_param(output_id))


def build_item_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.GIVE_ITEM: apply_give_item,
        InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE: apply_give_from_loot_table,
        InteractionEffectTypeEnum.REMOVE_ITEM: apply_remove_item,
        InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT: apply_deposit_item_to_object,
        InteractionEffectTypeEnum.COMBINE_ITEMS: apply_combine_items,
    }
