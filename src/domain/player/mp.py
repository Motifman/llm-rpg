from dataclasses import dataclass

@dataclass(frozen=True)
class Mp:
    value: int
    max_mp: int

    def __post_init__(self):
        if self.value < 0:
            self.value = 0
        if self.value > self.max_mp:
            self.value = self.max_mp

    def heal(self, amount: int) -> "Mp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Mp(self.value + amount, self.max_mp)

    def damage(self, amount: int) -> "Mp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Mp(self.value - amount, self.max_mp)

    def is_empty(self) -> bool:
        return self.value <= 0

    def can_consume(self, amount: int) -> bool:
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return self.value >= amount