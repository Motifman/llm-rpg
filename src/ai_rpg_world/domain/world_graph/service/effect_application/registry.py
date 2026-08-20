from __future__ import annotations

from typing import Callable, Mapping

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    UnsupportedInteractionEffectException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)


EffectHandlerFn = Callable[[InteractionEffect, EffectApplicationState], None]


def validate_handler_coverage(
    handlers: Mapping[InteractionEffectTypeEnum, EffectHandlerFn],
) -> None:
    """RESOLVE_ONGOING_CONDITION 以外の全効果種別に handler があるか検査する。"""
    expected = {
        et
        for et in InteractionEffectTypeEnum
        if et is not InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION
    }
    missing = expected - set(handlers.keys())
    if missing:
        raise AssertionError(
            f"handler registry に未登録の InteractionEffectTypeEnum: "
            f"{sorted(missing, key=lambda e: e.value)}"
        )


def dispatch_effect(
    handlers: Mapping[InteractionEffectTypeEnum, EffectHandlerFn],
    effect: InteractionEffect,
    ctx: EffectApplicationState,
) -> None:
    """registry から handler を引き、効果を適用する。"""
    handler = handlers.get(effect.effect_type)
    if handler is None:
        raise UnsupportedInteractionEffectException(
            f"Unsupported interaction effect: {effect.effect_type.value}"
        )
    handler(effect, ctx)
