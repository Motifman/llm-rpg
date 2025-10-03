from dataclasses import dataclass

@dataclass(frozen=True)
class Hp:
    value: int
    max_hp: int

    def __post_init__(self):
        if self.max_hp < 0:
            raise ValueError(f"max_hp must be >= 0: {self.max_hp}")
        # valueを適切な範囲に制限
        actual_value = max(0, min(self.value, self.max_hp))
        if actual_value != self.value:
            raise ValueError(f"value must be between 0 and max_hp: value={self.value}, max_hp={self.max_hp}")

    @classmethod
    def create(cls, value: int, max_hp: int) -> "Hp":
        """HPを作成するファクトリメソッド"""
        if max_hp < 0:
            raise ValueError(f"max_hp must be >= 0: {max_hp}")
        actual_value = max(0, min(value, max_hp))
        return cls(actual_value, max_hp)

    def heal(self, amount: int) -> "Hp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Hp.create(self.value + amount, self.max_hp)

    def damage(self, amount: int) -> "Hp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Hp.create(self.value - amount, self.max_hp)

    def can_consume(self, amount: int) -> bool:
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return self.value >= amount

    def is_alive(self) -> bool:
        return self.value > 0