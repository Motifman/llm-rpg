from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.cross_domain import (
    build_cross_domain_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.flags import (
    build_flag_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.item_instance import (
    build_item_instance_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.items import (
    build_item_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.messages import (
    build_message_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.object_state import (
    build_object_state_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.player_state import (
    build_player_state_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    EffectHandlerFn,
    validate_handler_coverage,
)


def build_effect_handlers() -> dict[InteractionEffectTypeEnum, EffectHandlerFn]:
    """全 InteractionEffectTypeEnum 向け handler を構築する。"""
    handlers: dict[InteractionEffectTypeEnum, EffectHandlerFn] = {}
    for partial in (
        build_flag_handlers(),
        build_message_handlers(),
        build_item_handlers(),
        build_object_state_handlers(),
        build_item_instance_handlers(),
        build_player_state_handlers(),
        build_cross_domain_handlers(),
    ):
        handlers.update(partial)
    validate_handler_coverage(handlers)
    return handlers
