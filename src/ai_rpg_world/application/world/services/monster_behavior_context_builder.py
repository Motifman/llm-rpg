from typing import Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.value_object.behavior_context import (
    GrowthContext,
    SkillSelectionContext,
)


class MonsterBehaviorContextBuilder:
    """monster behavior 用の skill/growth context を構築する。"""

    def __init__(self, monster_repository: MonsterRepository | None) -> None:
        self._monster_repository = monster_repository

    def build_skill_context(
        self,
        actor: WorldObject,
        current_tick: WorldTick,
    ) -> Optional[SkillSelectionContext]:
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None
        if self._monster_repository is None:
            return None

        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if monster is None:
            return None

        usable_slot_indices: set[int] = set()
        for skill_info in actor.component.available_skills:
            if monster.skill_loadout.can_use_skill(
                skill_info.slot_index,
                current_tick.value,
            ):
                usable_slot_indices.add(skill_info.slot_index)
        return SkillSelectionContext(usable_slot_indices=usable_slot_indices)

    def build_growth_context(
        self,
        actor: WorldObject,
        current_tick: WorldTick,
    ) -> Optional[GrowthContext]:
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None
        if self._monster_repository is None:
            return None

        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if monster is None or not monster.template.growth_stages:
            return None

        return GrowthContext(
            effective_flee_threshold=monster.get_effective_flee_threshold(current_tick),
            allow_chase=monster.get_allow_chase(current_tick),
        )
