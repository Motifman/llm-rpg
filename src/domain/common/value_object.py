from dataclasses import dataclass

@dataclass(frozen=True)
class Exp:
    value: int

    def __post_init__(self):
        if self.value < 0:
            raise ValueError(f"Invalid amount: {self.value}")
    
    def __add__(self, exp: "Exp") -> "Exp":
        return Exp(self.value + exp.value)
    
    def __sub__(self, exp: "Exp") -> "Exp":
        return Exp(self.value - exp.value)
    
    def __gt__(self, exp: "Exp") -> bool:
        return self.value > exp.value

    def __ge__(self, exp: "Exp") -> bool:
        return self.value >= exp.value
    

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
    
    def __gt__(self, gold: "Gold") -> bool:
        return self.value > gold.value

    def __ge__(self, gold: "Gold") -> bool:
        return self.value >= gold.value
    
    def __str__(self) -> str:
        return str(self.value)
    
    def __repr__(self) -> str:
        return f"Gold({self.value})"


@dataclass(frozen=True)
class Level:
    value: int

    def __post_init__(self):
        if self.value < 1:
            raise ValueError(f"Invalid level: {self.value}")
        if self.value > 99:
            # frozen=Trueなので、object.__setattr__を使用して値を設定
            object.__setattr__(self, 'value', 99)
    
    def up(self) -> "Level":
        return Level(self.value + 1)
    
    def __ge__(self, level: "Level") -> bool:
        return self.value >= level.value
    
    def __str__(self) -> str:
        return str(self.value)
    
    def __repr__(self) -> str:
        return f"Level({self.value})"