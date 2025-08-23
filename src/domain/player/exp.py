from dataclasses import dataclass

@dataclass(frozen=True)
class Exp:
    value: int
    max_exp: int

    def __post_init__(self):
        if self.value < 0:
            raise ValueError(f"Invalid amount: {self.value}")
        if self.value > self.max_exp:
            self.value = self.max_exp
    
    def __add__(self, exp: "Exp") -> "Exp":
        return Exp(self.value + exp.value, self.max_exp)
    
    def __sub__(self, exp: "Exp") -> "Exp":
        return Exp(self.value - exp.value, self.max_exp)

    def __ge__(self, exp: "Exp") -> bool:
        return self.value >= exp.value
    
    def is_max(self) -> bool:
        return self.value >= self.max_exp
    
    def is_min(self) -> bool:
        return self.value <= 0