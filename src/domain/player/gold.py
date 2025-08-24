from dataclasses import dataclass

@dataclass(frozen=True)
class Gold:
    value: int

    def __post_init__(self):
        if self.value < 0:
            raise ValueError(f"Invalid amount: {self.value}")

    def __add__(self, gold: "Gold") -> "Gold":
        return Gold(self.value + gold.value)

    def __sub__(self, gold: "Gold") -> "Gold":
        return Gold(self.value - gold.value)

    def __ge__(self, gold: "Gold") -> bool:
        return self.value >= gold.value
    
    def __str__(self) -> str:
        return str(self.value)
    
    def __repr__(self) -> str:
        return f"Gold({self.value})"