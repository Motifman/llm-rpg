"""
スキル選択ポリシー。
攻撃時に使用するスキルスロットを決定するルールを抽象化する。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.entity.world_object_component import MonsterSkillInfo

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.world_object import WorldObject


class SkillSelectionPolicy(ABC):
    """
    ターゲットが射程内にいる場合に、使用するスキルスロットを選択するポリシーのインターフェース。
    """

    @abstractmethod
    def select_slot(
        self,
        actor: "WorldObject",
        target: "WorldObject",
        available_skills: List[MonsterSkillInfo],
    ) -> Optional[int]:
        """
        使用するスキルのスロットインデックスを選択する。

        Args:
            actor: 行動主体のワールドオブジェクト
            target: 攻撃対象のワールドオブジェクト
            available_skills: 利用可能なスキル情報のリスト

        Returns:
            使用するスキルの slot_index。使用しない場合は None
        """
        pass


class FirstInRangeSkillPolicy(SkillSelectionPolicy):
    """
    射程内にある最初のスキルを選択するポリシー。
    available_skills の先頭から順に射程を確認し、最初に条件を満たしたスキルを返す。
    """

    def select_slot(
        self,
        actor: "WorldObject",
        target: "WorldObject",
        available_skills: List[MonsterSkillInfo],
    ) -> Optional[int]:
        if not available_skills:
            return None
        distance = actor.coordinate.distance_to(target.coordinate)
        for skill in available_skills:
            if distance <= skill.range:
                return skill.slot_index
        return None
