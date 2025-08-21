from dataclasses import dataclass


@dataclass(frozen=True)
class Durability:
    durability: int
    max_durability: int
    
    def __post_init__(self):
        if self.durability < 0 or self.durability > self.max_durability:
            raise ValueError(f"durability must be >= 0 and <= max_durability. durability: {self.durability}, max_durability: {self.max_durability}")
    
    def damage(self, amount: int) -> int:
        if amount < 0:
            raise ValueError(f"amount must be >= 0. amount: {amount}")
        self.durability = max(0, self.durability - amount)
        return self.durability
    
    def repair(self, amount: int) -> int:
        if amount < 0:
            raise ValueError(f"amount must be >= 0. amount: {amount}")
        self.durability = min(self.durability + amount, self.max_durability)
        return self.durability
    
    def is_broken(self) -> bool:
        return self.durability <= 0