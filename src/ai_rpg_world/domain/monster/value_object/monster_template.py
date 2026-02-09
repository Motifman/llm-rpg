from dataclasses import dataclass
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException


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

    def __post_init__(self):
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
