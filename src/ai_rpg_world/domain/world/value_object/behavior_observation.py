"""
行動決定の入力となる「観測」を表す値オブジェクト。
視界内の脅威・敵対・選択ターゲット、スキル/成長/ターゲット選択の補助情報、パック集結座標・現在ティックを保持する。
ドメイン層で組み立てる部分（視界・脅威・敵対・選択ターゲット）と、
アプリケーション層から渡される部分（skill_context, growth_context, target_context, pack_rally_coordinate, current_tick）を区別する。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from ai_rpg_world.domain.world.value_object.behavior_context import (
    GrowthContext,
    SkillSelectionContext,
    TargetSelectionContext,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.value_object import WorldTick
    from ai_rpg_world.domain.world.entity.world_object import WorldObject


@dataclass(frozen=True)
class BehaviorObservation:
    """
    アクターがこの tick で得ている観測。
    - visible_threats / visible_hostiles / selected_target: ドメインロジック（BehaviorService）で算出。
    - skill_context / growth_context / target_context / pack_rally_coordinate / current_tick: アプリ層がリポジトリ等から組み立てて渡す。
    """
    visible_threats: list["WorldObject"] = field(default_factory=list)
    visible_hostiles: list["WorldObject"] = field(default_factory=list)
    selected_target: Optional["WorldObject"] = None
    visible_feed: list["WorldObject"] = field(default_factory=list)
    selected_feed_target: Optional["WorldObject"] = None
    skill_context: SkillSelectionContext | None = None
    growth_context: GrowthContext | None = None
    target_context: TargetSelectionContext | None = None
    pack_rally_coordinate: Coordinate | None = None
    current_tick: Optional["WorldTick"] = None
