from dataclasses import dataclass
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterStatsValidationException


@dataclass(frozen=True)
class MonsterHp:
    """モンスターのHP値オブジェクト"""
    value: int
    max_hp: int

    def __post_init__(self):
        if self.max_hp < 0:
            raise MonsterStatsValidationException(f"max_hp must be non-negative: {self.max_hp}")
        if self.value > self.max_hp:
            raise MonsterStatsValidationException(
                f"HP ({self.value}) cannot exceed max_hp ({self.max_hp})"
            )
        if self.value < 0:
            raise MonsterStatsValidationException(f"HP cannot be negative: {self.value}")

    @classmethod
    def create(cls, value: int, max_hp: int) -> "MonsterHp":
        actual_value = max(0, min(value, max_hp))
        return cls(actual_value, max_hp)

    def damage(self, amount: int) -> "MonsterHp":
        if amount < 0:
            raise MonsterStatsValidationException(f"Damage amount cannot be negative: {amount}")
        return MonsterHp.create(self.value - amount, self.max_hp)

    def heal(self, amount: int) -> "MonsterHp":
        if amount < 0:
            raise MonsterStatsValidationException(f"Heal amount cannot be negative: {amount}")
        return MonsterHp.create(self.value + amount, self.max_hp)

    def is_alive(self) -> bool:
        return self.value > 0

    def get_percentage(self) -> float:
        if self.max_hp == 0:
            return 0.0
        return self.value / self.max_hp
