"""
状態遷移の入力となる「現在の行動状態」のスナップショット。
Component または（Phase 3 以降）Monster 集約から生成し、
BehaviorStateTransitionService に渡す。
"""

from dataclasses import dataclass
from typing import List, Optional

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum


@dataclass(frozen=True)
class BehaviorStateSnapshot:
    """
    状態遷移ルールが参照する現在状態の読み取り専用スナップショット。
    リポジトリに依存せず、呼び出し元が Component または Monster から組み立てる。
    """
    state: BehaviorStateEnum
    target_id: Optional[WorldObjectId] = None
    last_known_target_position: Optional[Coordinate] = None
    hp_percentage: float = 1.0
    phase_thresholds: tuple = ()  # 0-index が ENRAGE 閾値
    flee_threshold: float = 0.0
