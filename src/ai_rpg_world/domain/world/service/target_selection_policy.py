"""
ターゲット選択ポリシー。
視界内の敵対候補から1体を選ぶルールを抽象化する。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

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
    ) -> Optional["WorldObject"]:
        """
        候補の中から1体のターゲットを選択する。

        Args:
            actor: 行動主体のワールドオブジェクト
            candidates: 視界内の敵対候補（空でない場合のみ呼ばれる想定）

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
    ) -> Optional["WorldObject"]:
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda obj: actor.coordinate.euclidean_distance_to(obj.coordinate),
        )
