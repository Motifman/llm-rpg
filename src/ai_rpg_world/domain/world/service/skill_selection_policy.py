"""
スキル選択ポリシー。
攻撃時に使用するスキルスロットを決定するルールを抽象化する。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo
from ai_rpg_world.domain.world.value_object.behavior_context import SkillSelectionContext

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
        context: Optional[SkillSelectionContext] = None,
    ) -> Optional[int]:
        """
        使用するスキルのスロットインデックスを選択する。

        Args:
            actor: 行動主体のワールドオブジェクト
            target: 攻撃対象のワールドオブジェクト
            available_skills: 利用可能なスキル情報のリスト
            context: 使用可能スロット・射程内ターゲット数等。省略可

        Returns:
            使用するスキルの slot_index。使用しない場合は None
        """
        pass


class FirstInRangeSkillPolicy(SkillSelectionPolicy):
    """
    射程内にある最初のスキルを選択するポリシー。
    context.usable_slot_indices が渡された場合はそのスロットに限定する。
    """

    def select_slot(
        self,
        actor: "WorldObject",
        target: "WorldObject",
        available_skills: List[MonsterSkillInfo],
        context: Optional[SkillSelectionContext] = None,
    ) -> Optional[int]:
        if not available_skills:
            return None
        distance = actor.coordinate.distance_to(target.coordinate)
        usable = context.usable_slot_indices if context else None
        for skill in available_skills:
            if usable is not None and skill.slot_index not in usable:
                continue
            if distance <= skill.range:
                return skill.slot_index
        return None


class BossSkillPolicy(SkillSelectionPolicy):
    """
    ボス用スキル選択。複数体が射程内ならAOEを優先し、使用可能スロットのみから選ぶ。
    context で usable_slot_indices と targets_in_range_by_slot を渡す想定。
    """

    def select_slot(
        self,
        actor: "WorldObject",
        target: "WorldObject",
        available_skills: List[MonsterSkillInfo],
        context: Optional[SkillSelectionContext] = None,
    ) -> Optional[int]:
        if not available_skills:
            return None
        distance = actor.coordinate.distance_to(target.coordinate)
        in_range_skills = [
            s for s in available_skills
            if distance <= s.range
        ]
        if not in_range_skills:
            return None
        usable = context.usable_slot_indices if context else None
        if usable is not None:
            in_range_skills = [s for s in in_range_skills if s.slot_index in usable]
        if not in_range_skills:
            return None
        targets_by_slot = context.targets_in_range_by_slot if context else {}
        if targets_by_slot:
            best = max(
                in_range_skills,
                key=lambda s: targets_by_slot.get(s.slot_index, 0),
            )
            return best.slot_index
        return in_range_skills[0].slot_index
