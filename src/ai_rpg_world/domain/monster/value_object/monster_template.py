from dataclasses import dataclass
from typing import List, Optional, Set
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.world.enum.world_enum import EcologyTypeEnum, ActiveTimeType


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
    behavior_strategy_type: str = "default"
    phase_thresholds: Optional[List[float]] = None
    ecology_type: EcologyTypeEnum = EcologyTypeEnum.NORMAL
    ambush_chase_range: Optional[int] = None
    territory_radius: Optional[int] = None
    active_time: ActiveTimeType = ActiveTimeType.ALWAYS
    threat_races: Optional[Set[str]] = None
    prey_races: Optional[Set[str]] = None

    def __post_init__(self):
        object.__setattr__(self, "skill_ids", self.skill_ids or [])
        object.__setattr__(self, "phase_thresholds", self.phase_thresholds or [])
        object.__setattr__(self, "threat_races", self.threat_races or frozenset())
        object.__setattr__(self, "prey_races", self.prey_races or frozenset())
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
        for i, t in enumerate(self.phase_thresholds):
            if not (0.0 <= t <= 1.0):
                raise MonsterTemplateValidationException(
                    f"phase_thresholds[{i}] must be between 0.0 and 1.0: {t}"
                )
        if self.ambush_chase_range is not None and self.ambush_chase_range < 0:
            raise MonsterTemplateValidationException(
                f"ambush_chase_range cannot be negative: {self.ambush_chase_range}"
            )
        if self.territory_radius is not None and self.territory_radius < 0:
            raise MonsterTemplateValidationException(
                f"territory_radius cannot be negative: {self.territory_radius}"
            )
        if not isinstance(self.ecology_type, EcologyTypeEnum):
            raise MonsterTemplateValidationException(
                f"ecology_type must be EcologyTypeEnum, got {type(self.ecology_type).__name__}"
            )
        if not isinstance(self.active_time, ActiveTimeType):
            raise MonsterTemplateValidationException(
                f"active_time must be ActiveTimeType, got {type(self.active_time).__name__}"
            )
        if self.threat_races is not None and not isinstance(self.threat_races, (set, frozenset)):
            raise MonsterTemplateValidationException(
                f"threat_races must be a set or frozenset, got {type(self.threat_races).__name__}"
            )
        if self.prey_races is not None and not isinstance(self.prey_races, (set, frozenset)):
            raise MonsterTemplateValidationException(
                f"prey_races must be a set or frozenset, got {type(self.prey_races).__name__}"
            )
