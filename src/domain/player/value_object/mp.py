from dataclasses import dataclass

@dataclass(frozen=True)
class Mp:
    value: int
    max_mp: int

    def __post_init__(self):
        if self.max_mp < 0:
            raise ValueError(f"max_mp must be >= 0: {self.max_mp}")
        # valueを適切な範囲に制限
        actual_value = max(0, min(self.value, self.max_mp))
        if actual_value != self.value:
            raise ValueError(f"value must be between 0 and max_mp: value={self.value}, max_mp={self.max_mp}")

    @classmethod
    def create(cls, value: int, max_mp: int) -> "Mp":
        """MPを作成するファクトリメソッド"""
        if max_mp < 0:
            raise ValueError(f"max_mp must be >= 0: {max_mp}")
        actual_value = max(0, min(value, max_mp))
        return cls(actual_value, max_mp)

    def heal(self, amount: int) -> "Mp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Mp.create(self.value + amount, self.max_mp)

    def consumed(self, amount: int) -> "Mp":
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return Mp.create(self.value - amount, self.max_mp)

    def can_consume(self, amount: int) -> bool:
        if amount < 0:
            raise ValueError(f"Invalid amount: {amount}")
        return self.value >= amount

    def is_empty(self) -> bool:
        return self.value <= 0