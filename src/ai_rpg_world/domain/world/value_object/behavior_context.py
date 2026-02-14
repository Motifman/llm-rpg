"""
行動決定に用いるコンテキスト（ターゲット選択・スキル選択で利用）。
アプリケーション層がHP・脅威値・利用可能スロット等を渡すための値オブジェクト。
"""

from dataclasses import dataclass, field
from typing import Dict, Set

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


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
