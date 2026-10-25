"""
モンスター集約が現在の行動状態を公開する読み取り専用のスナップショット。
"""

from dataclasses import dataclass

from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class BehaviorStateSnapshot:
    """
    状態遷移ルールが参照する現在状態の読み取り専用スナップショット。
    リポジトリに依存せず、モンスター集約から組み立てる。
    """
    state: BehaviorStateEnum
    target_id: WorldObjectId | None = None
    last_known_target_position: Coordinate | None = None
    hp_percentage: float = 1.0
    phase_thresholds: tuple[float, ...] = ()  # 0-index が ENRAGE 閾値
    flee_threshold: float = 0.0
