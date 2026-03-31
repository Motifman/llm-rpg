from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum


@dataclass(frozen=True)
class GameEndCondition:
    """ゲーム終了条件（脱出ゲーム等）"""

    condition_type: GameEndConditionTypeEnum
    target_spot_id: Optional[SpotId] = None
    target_flag: Optional[str] = None
    tick_limit: Optional[int] = None
