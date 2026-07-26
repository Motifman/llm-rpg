from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

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
    # SURVIVING_PLAYERS_WITH_STATE_AT_MOST 用。数える対象を選ぶ state と、
    # 「これ以下になったら成立」の閾値。
    required_state: Optional[Mapping[str, Any]] = None
    max_surviving: Optional[int] = None

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
        if (
            self.condition_type
            is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST
        ):
            if not self.required_state:
                raise GameEndConditionValidationException(
                    "SURVIVING_PLAYERS_WITH_STATE_AT_MOST には required_state が"
                    "必要です (誰を数えるかが決まりません)"
                )
            if self.max_surviving is None:
                # 0 を既定にすると「書き忘れ」と「全滅を指定した」が
                # 区別できなくなる。
                raise GameEndConditionValidationException(
                    "SURVIVING_PLAYERS_WITH_STATE_AT_MOST には max_surviving が"
                    "必要です"
                )
            if int(self.max_surviving) < 0:
                raise GameEndConditionValidationException(
                    "max_surviving は 0 以上である必要があります "
                    f"(負の閾値は成立しえません): {self.max_surviving}"
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
