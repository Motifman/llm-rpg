from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    EffectHandlerFn,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)


def apply_set_flag(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    name = effect.parameters.get("flag_name")
    if isinstance(name, str):
        ctx.flags.add(name)


def apply_clear_flag(effect: InteractionEffect, ctx: EffectApplicationState) -> None:
    name = effect.parameters.get("flag_name")
    if isinstance(name, str):
        ctx.flags.discard(name)


def build_flag_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    return {
        InteractionEffectTypeEnum.SET_FLAG: apply_set_flag,
        InteractionEffectTypeEnum.CLEAR_FLAG: apply_clear_flag,
    }
