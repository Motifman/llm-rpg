"""
行動決定の入力となる「観測」を表す値オブジェクト。
視界内の脅威・敵対・選択ターゲット、スキル/成長/ターゲット選択の補助情報、パック集結座標・現在ティックを保持する。
ドメイン層で組み立てる部分（視界・脅威・敵対・選択ターゲット）と、
アプリケーション層から渡される部分（skill_context, growth_context, target_context, pack_rally_coordinate, current_tick）を区別する。
"""

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_context import (
    TargetSelectionContext,
    SkillSelectionContext,
    GrowthContext,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.world_object import WorldObject
    from ai_rpg_world.domain.common.value_object import WorldTick


@dataclass(frozen=True)
class BehaviorObservation:
    """
    アクターがこの tick で得ている観測。
    - visible_threats / visible_hostiles / selected_target: ドメインロジック（BehaviorService）で算出。
    - skill_context / growth_context / target_context / pack_rally_coordinate / current_tick: アプリ層がリポジトリ等から組み立てて渡す。
    """
    visible_threats: List["WorldObject"] = field(default_factory=list)
    visible_hostiles: List["WorldObject"] = field(default_factory=list)
    selected_target: Optional["WorldObject"] = None
    visible_feed: List["WorldObject"] = field(default_factory=list)
    selected_feed_target: Optional["WorldObject"] = None
    skill_context: Optional[SkillSelectionContext] = None
    growth_context: Optional[GrowthContext] = None
    target_context: Optional[TargetSelectionContext] = None
    pack_rally_coordinate: Optional[Coordinate] = None
    current_tick: Optional["WorldTick"] = None
