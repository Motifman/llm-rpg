from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


@dataclass(frozen=True)
class InteractionDef:
    action_name: str
    display_label: str
    preconditions: Tuple[InteractionCondition, ...]
    effects: Tuple[InteractionEffect, ...]
