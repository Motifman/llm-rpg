from dataclasses import dataclass


@dataclass(frozen=True)
class Durability:
    durability: int
    max_durability: int
    
    def __post_init__(self):
        if self.durability < 0 or self.durability > self.max_durability:
            raise ValueError(f"durability must be >= 0 and <= max_durability. durability: {self.durability}, max_durability: {self.max_durability}")
    
    def damage(self, amount: int) -> 'Durability':
        if amount < 0:
            raise ValueError(f"amount must be >= 0. amount: {amount}")
        new_durability = max(0, self.durability - amount)
        return Durability(new_durability, self.max_durability)
    
    def repair(self, amount: int) -> 'Durability':
        if amount < 0:
            raise ValueError(f"amount must be >= 0. amount: {amount}")
        new_durability = min(self.durability + amount, self.max_durability)
        return Durability(new_durability, self.max_durability)
    
    def is_broken(self) -> bool:
        return self.durability <= 0