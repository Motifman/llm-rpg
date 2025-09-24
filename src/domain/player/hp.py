from dataclasses import dataclass

@dataclass
class Hp:
    value: int
    max_hp: int

    def __post_init__(self):
        if self.value < 0:
            self.value = 0
        if self.value > self.max_hp:
            self.value = self.max_hp

    def heal(self, amount: int) -> "Hp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Hp(self.value + amount, self.max_hp)

    def damage(self, amount: int) -> "Hp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Hp(self.value - amount, self.max_hp)
    
    def can_consume(self, amount: int) -> bool:
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return self.value >= amount

    def is_alive(self) -> bool:
        return self.value > 0