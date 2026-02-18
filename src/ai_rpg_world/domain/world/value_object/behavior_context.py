"""
行動決定に用いるコンテキスト（ターゲット選択・スキル選択・成長段階で利用）。
アプリケーション層がHP・脅威値・利用可能スロット・成長段階に応じた行動パラメータ等を渡すための値オブジェクト。
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.exception.behavior_exception import GrowthContextValidationException

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.world_object import WorldObject
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
    from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent


@dataclass(frozen=True)
class TargetSelectionContext:
    """
    ターゲット選択の補助情報（ボスAI等で利用）。
    与ダメージ・HP% 等はアプリ層が集約し渡す。
    """
    hp_percentage_by_id: Dict[WorldObjectId, float] = field(default_factory=dict)
    threat_by_id: Dict[WorldObjectId, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSelectionContext:
    """
    スキル選択の補助情報（MP・クールダウン・射程内ターゲット数等）。
    アプリ層が「使用可能なスロット」と「スロットごとの射程内ターゲット数」を渡す。
    """
    usable_slot_indices: Set[int] = field(default_factory=set)
    targets_in_range_by_slot: Dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GrowthContext:
    """
    成長段階に応じた行動制御の補助情報。
    幼体は FLEE 閾値を上げ・CHASE しない等をアプリ層が MonsterAggregate から取得して渡す。
    値オブジェクトとして不正な値を許容しない（effective_flee_threshold は 0.0〜1.0、allow_chase は bool）。
    """
    effective_flee_threshold: float  # この tick で使う FLEE 閾値（0.0〜1.0）
    allow_chase: bool  # CHASE（追跡）を許可するか

    def __post_init__(self) -> None:
        if not isinstance(self.effective_flee_threshold, (int, float)):
            raise GrowthContextValidationException(
                f"effective_flee_threshold must be a number, got {type(self.effective_flee_threshold).__name__}"
            )
        if not (0.0 <= self.effective_flee_threshold <= 1.0):
            raise GrowthContextValidationException(
                f"effective_flee_threshold must be between 0.0 and 1.0: {self.effective_flee_threshold}"
            )
        if not isinstance(self.allow_chase, bool):
            raise GrowthContextValidationException(
                f"allow_chase must be a bool, got {type(self.allow_chase).__name__}"
            )


@dataclass
class PlanActionContext:
    """
    行動計画（状態更新・アクション決定）に必要なコンテキストを一括で渡すための値オブジェクト。
    BehaviorService が収集し、戦略の update_state / decide_action に渡す。
    """
    actor_id: WorldObjectId
    actor: "WorldObject"
    map_aggregate: "PhysicalMapAggregate"
    component: "AutonomousBehaviorComponent"
    visible_threats: List["WorldObject"]
    visible_hostiles: List["WorldObject"]
    target: Optional["WorldObject"]
    target_context: Optional[TargetSelectionContext] = None
    skill_context: Optional[SkillSelectionContext] = None
    pack_rally_coordinate: Optional[Coordinate] = None
    growth_context: Optional[GrowthContext] = None
