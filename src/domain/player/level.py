from dataclasses import dataclass

@dataclass(frozen=True)
class Level:
    value: int

    def __post_init__(self):
        if self.value < 1:
            raise ValueError(f"Invalid level: {self.value}")
        if self.value > 99:
            self.value = 99
    
    def up(self) -> "Level":
        return Level(self.value + 1)
    
    def __ge__(self, level: "Level") -> bool:
        return self.value >= level.value