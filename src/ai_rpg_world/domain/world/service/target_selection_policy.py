"""
ターゲット選択ポリシー。
視界内の敵対候補から1体を選ぶルールを抽象化する。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.behavior_context import TargetSelectionContext

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.world_object import WorldObject


class TargetSelectionPolicy(ABC):
    """
    視界内の敵対候補からターゲットを1体選択するポリシーのインターフェース。
    """

    @abstractmethod
    def select_target(
        self,
        actor: "WorldObject",
        candidates: List["WorldObject"],
        context: Optional[TargetSelectionContext] = None,
    ) -> Optional["WorldObject"]:
        """
        候補の中から1体のターゲットを選択する。

        Args:
            actor: 行動主体のワールドオブジェクト
            candidates: 視界内の敵対候補（空でない場合のみ呼ばれる想定）
            context: ターゲット選択の補助情報（HP%・脅威値等）。省略時は距離のみで判定

        Returns:
            選択されたターゲット。選択しない場合は None
        """
        pass


class NearestTargetPolicy(TargetSelectionPolicy):
    """
    最も近い敵対オブジェクトをターゲットとして選択するポリシー。
    ユークリッド距離で比較する。
    """

    def select_target(
        self,
        actor: "WorldObject",
        candidates: List["WorldObject"],
        context: Optional[TargetSelectionContext] = None,
    ) -> Optional["WorldObject"]:
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda obj: actor.coordinate.euclidean_distance_to(obj.coordinate),
        )


class HighestThreatTargetPolicy(TargetSelectionPolicy):
    """
    脅威値（与ダメージ等）が最も高い候補を選択するポリシー。
    context.threat_by_id が渡されない場合は NearestTargetPolicy と同様に最近距離を選ぶ。
    """

    def select_target(
        self,
        actor: "WorldObject",
        candidates: List["WorldObject"],
        context: Optional[TargetSelectionContext] = None,
    ) -> Optional["WorldObject"]:
        if not candidates:
            return None
        if context and context.threat_by_id:
            return max(
                candidates,
                key=lambda obj: context.threat_by_id.get(obj.object_id, 0),
            )
        return min(
            candidates,
            key=lambda obj: actor.coordinate.euclidean_distance_to(obj.coordinate),
        )


class LowestHpTargetPolicy(TargetSelectionPolicy):
    """
    HP% が最も低い候補を選択するポリシー（しつこく狙う）。
    context.hp_percentage_by_id が渡されない場合は NearestTargetPolicy と同様に最近距離を選ぶ。
    """

    def select_target(
        self,
        actor: "WorldObject",
        candidates: List["WorldObject"],
        context: Optional[TargetSelectionContext] = None,
    ) -> Optional["WorldObject"]:
        if not candidates:
            return None
        if context and context.hp_percentage_by_id:
            return min(
                candidates,
                key=lambda obj: context.hp_percentage_by_id.get(obj.object_id, 1.0),
            )
        return min(
            candidates,
            key=lambda obj: actor.coordinate.euclidean_distance_to(obj.coordinate),
        )
