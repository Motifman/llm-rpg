"""効果ハンドラ registry の網羅性と未登録 dispatch を検証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    UnsupportedInteractionEffectException,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers import (
    build_effect_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    dispatch_effect,
    validate_handler_coverage,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior


class TestEffectHandlerRegistryCoverage:
    """InteractionEffectTypeEnum と handler registry の対応を保証する。"""

    def test_all_effect_types_except_resolve_ongoing_have_handlers(self) -> None:
        """RESOLVE_ONGOING_CONDITION 以外の全 InteractionEffectTypeEnum に handler がある。"""
        handlers = build_effect_handlers()
        validate_handler_coverage(handlers)
        expected = {
            et
            for et in InteractionEffectTypeEnum
            if et is not InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION
        }
        assert set(handlers.keys()) == expected

    def test_unregistered_effect_raises_unsupported_exception(self) -> None:
        """registry に無い効果種別を apply しようとすると UnsupportedInteractionEffectException になる。"""
        handlers = build_effect_handlers()
        ctx = EffectApplicationState(
            interior=SpotInterior.empty(),
            acting_object=None,
            flags=set(),
        )
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION,
            parameters={"flag": "test"},
        )
        with pytest.raises(UnsupportedInteractionEffectException):
            dispatch_effect(handlers, effect, ctx)
