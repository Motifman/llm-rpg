from dataclasses import dataclass
from typing import Optional, Union
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRewardValidationException
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


@dataclass(frozen=True)
class RewardInfo:
    """モンスター討伐時の報酬情報"""
    exp: int
    gold: int
    loot_table_id: Optional[LootTableId] = None

    def __post_init__(self) -> None:
        if self.exp < 0:
            raise MonsterRewardValidationException(f"EXP cannot be negative: {self.exp}")
        if self.gold < 0:
            raise MonsterRewardValidationException(f"Gold cannot be negative: {self.gold}")
        if self.loot_table_id is not None and not isinstance(self.loot_table_id, LootTableId):
            object.__setattr__(self, "loot_table_id", LootTableId.create(self.loot_table_id))
