from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum


@dataclass(frozen=True)
class InteractionEffect:
    effect_type: InteractionEffectTypeEnum
    parameters: Dict[str, Any]
