from dataclasses import dataclass
from typing import List
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId


@dataclass(frozen=True)
class MonsterTemplate:
    """モンスターの種族・定義情報"""
    template_id: MonsterTemplateId
    name: str
    base_stats: BaseStats
    reward_info: RewardInfo
    respawn_info: RespawnInfo
    race: Race
    faction: MonsterFactionEnum
    description: str
    skill_ids: List[SkillId] = None
    vision_range: int = 5
    flee_threshold: float = 0.2

    def __post_init__(self):
        object.__setattr__(self, "skill_ids", self.skill_ids or [])
        if not isinstance(self.skill_ids, list):
            raise MonsterTemplateValidationException(
                f"skill_ids must be a list, got {type(self.skill_ids).__name__}"
            )
        for i, e in enumerate(self.skill_ids):
            if not isinstance(e, SkillId):
                raise MonsterTemplateValidationException(
                    f"skill_ids[{i}] must be SkillId, got {type(e).__name__}"
                )
        if not self.name or not self.name.strip():
            raise MonsterTemplateValidationException("Monster name cannot be empty")
        
        if not self.description or not self.description.strip():
            raise MonsterTemplateValidationException("Monster description cannot be empty")
        
        if len(self.description) > 1000:
            raise MonsterTemplateValidationException("Monster description is too long (max 1000 characters)")
        
        if not isinstance(self.race, Race):
            raise MonsterTemplateValidationException(f"Invalid race: {self.race}")
            
        if not isinstance(self.faction, MonsterFactionEnum):
            raise MonsterTemplateValidationException(f"Invalid faction: {self.faction}")

        if self.vision_range < 0:
            raise MonsterTemplateValidationException(
                f"vision_range cannot be negative: {self.vision_range}"
            )
        if not (0.0 <= self.flee_threshold <= 1.0):
            raise MonsterTemplateValidationException(
                f"flee_threshold must be between 0.0 and 1.0: {self.flee_threshold}"
            )
