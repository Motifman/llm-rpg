from dataclasses import dataclass
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
    MonsterInsufficientMpException
)


@dataclass(frozen=True)
class MonsterMp:
    """モンスターのMP値オブジェクト"""
    value: int
    max_mp: int

    def __post_init__(self):
        if self.max_mp < 0:
            raise MonsterStatsValidationException(f"max_mp must be non-negative: {self.max_mp}")
        if self.value > self.max_mp:
            raise MonsterStatsValidationException(
                f"MP ({self.value}) cannot exceed max_mp ({self.max_mp})"
            )
        if self.value < 0:
            raise MonsterStatsValidationException(f"MP cannot be negative: {self.value}")

    @classmethod
    def create(cls, value: int, max_mp: int) -> "MonsterMp":
        actual_value = max(0, min(value, max_mp))
        return cls(actual_value, max_mp)

    def use(self, amount: int) -> "MonsterMp":
        if amount < 0:
            raise MonsterStatsValidationException(f"Use amount cannot be negative: {amount}")
        if self.value < amount:
            raise MonsterInsufficientMpException(f"Insufficient MP: {self.value} < {amount}")
        return MonsterMp.create(self.value - amount, self.max_mp)

    def recover(self, amount: int) -> "MonsterMp":
        if amount < 0:
            raise MonsterStatsValidationException(f"Recover amount cannot be negative: {amount}")
        return MonsterMp.create(self.value + amount, self.max_mp)
