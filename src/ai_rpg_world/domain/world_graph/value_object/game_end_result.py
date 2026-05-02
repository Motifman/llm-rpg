from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum


@dataclass(frozen=True)
class GameEndResult:
    """ゲーム終了判定の結果"""

    is_ended: bool
    result: Optional[GameResultEnum]
    reason: str
