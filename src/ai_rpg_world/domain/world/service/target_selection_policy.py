"""
ターゲット選択ポリシー。
視界内の敵対候補から1体を選ぶルールを抽象化する。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.behavior_context import TargetSelectionContext
from ai_rpg_world.domain.world.service.hostility_service import HostilityService

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


class PackLeaderTargetPolicy(TargetSelectionPolicy):
    """
    群れのリーダーのターゲットを最優先する。context.pack_leader_target_id が
    候補に含まれていればそれを返し、そうでなければ fallback_policy に委譲する。
    """

    def __init__(self, fallback_policy: TargetSelectionPolicy):
        self._fallback_policy = fallback_policy

    def select_target(
        self,
        actor: "WorldObject",
        candidates: List["WorldObject"],
        context: Optional[TargetSelectionContext] = None,
    ) -> Optional["WorldObject"]:
        if not candidates:
            return None
        if context and context.pack_leader_target_id is not None:
            for c in candidates:
                if c.object_id == context.pack_leader_target_id:
                    return c
        return self._fallback_policy.select_target(actor, candidates, context)


class PreyPriorityTargetPolicy(TargetSelectionPolicy):
    """
    獲物(PREY)を優先し、同列ならフォールバックポリシーで選択する。
    HostilityService.is_prey で獲物を判定し、獲物がいればその中から fallback で1体選ぶ。
    """

    def __init__(
        self,
        hostility_service: HostilityService,
        fallback_policy: TargetSelectionPolicy,
    ):
        self._hostility_service = hostility_service
        self._fallback_policy = fallback_policy

    def select_target(
        self,
        actor: "WorldObject",
        candidates: List["WorldObject"],
        context: Optional[TargetSelectionContext] = None,
    ) -> Optional["WorldObject"]:
        if not candidates:
            return None
        actor_comp = actor.component
        preys = [c for c in candidates if self._hostility_service.is_prey(actor_comp, c.component)]
        pool = preys if preys else candidates
        return self._fallback_policy.select_target(actor, pool, context)
