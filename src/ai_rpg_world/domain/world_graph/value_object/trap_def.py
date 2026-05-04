"""トラップ（罠）定義の値オブジェクト。

SpotNode（進入トラップ）や SpotObject（操作トラップ）に付与する。
効果は InteractionEffect を再利用し、WorldGraphEffectService で処理する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.world_graph.enum.trap_trigger_type import TrapTriggerTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


@dataclass(frozen=True)
class TrapDef:
    trap_id: str
    trigger_type: TrapTriggerTypeEnum
    effects: Tuple[InteractionEffect, ...]
    is_hidden: bool = True
    is_repeating: bool = False
    disarm_conditions: Tuple[InteractionCondition, ...] = ()
    detection_difficulty: int = 0  # EXPLORE で発見可能（search_count >= この値）
