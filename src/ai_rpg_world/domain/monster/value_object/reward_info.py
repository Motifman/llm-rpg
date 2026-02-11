from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRewardValidationException


@dataclass(frozen=True)
class RewardInfo:
    """モンスター討伐時の報酬情報"""
    exp: int
    gold: int
    loot_table_id: Optional[str] = None

    def __post_init__(self):
        if self.exp < 0:
            raise MonsterRewardValidationException(f"EXP cannot be negative: {self.exp}")
        if self.gold < 0:
            raise MonsterRewardValidationException(f"Gold cannot be negative: {self.gold}")
