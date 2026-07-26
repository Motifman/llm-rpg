from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)


@dataclass(frozen=True)
class GameEndCondition:
    """ゲーム終了条件（脱出ゲーム等）"""

    condition_type: GameEndConditionTypeEnum
    target_spot_id: Optional[SpotId] = None
    target_flag: Optional[str] = None
    tick_limit: Optional[int] = None

    def __post_init__(self) -> None:
        """条件型ごとの必須フィールド欠落を構築時に拒否する。"""
        if self.condition_type == GameEndConditionTypeEnum.FLAG_SET:
            if not isinstance(self.target_flag, str) or not self.target_flag.strip():
                raise GameEndConditionValidationException(
                    "FLAG_SET には target_flag が必要です"
                )
            return
        if self.condition_type == GameEndConditionTypeEnum.TICK_LIMIT:
            if self.tick_limit is None:
                raise GameEndConditionValidationException(
                    "TICK_LIMIT には tick_limit が必要です"
                )
            return
        if self.condition_type in (
            GameEndConditionTypeEnum.ALL_AT_SPOT,
            GameEndConditionTypeEnum.ANY_AT_SPOT,
        ):
            if self.target_spot_id is None:
                raise GameEndConditionValidationException(
                    f"{self.condition_type.value} には target_spot_id が必要です"
                )
