from dataclasses import dataclass
from typing import Any

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
            raise ValueError(f"Level cannot exceed 99: {self.value}")

    @classmethod
    def create(cls, value: int) -> "Level":
        """Levelを作成するファクトリメソッド。レベル99を超える場合は99に制限"""
        if value < 1:
            raise ValueError(f"Invalid level: {value}")
        actual_value = min(value, 99)
        return cls(actual_value)

    def up(self) -> "Level":
        return Level.create(self.value + 1)

    def __ge__(self, level: "Level") -> bool:
        return self.value >= level.value

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Level({self.value})"


@dataclass(frozen=True)
class WorldTick:
    """ワールド内の時間を表す最小単位（ティック）"""
    value: int

    def __post_init__(self):
        if self.value < 0:
            raise ValueError(f"Invalid tick: {self.value}")

    def next(self) -> "WorldTick":
        """次のティックを返す"""
        return WorldTick(self.value + 1)

    def add_duration(self, duration: int) -> "WorldTick":
        """期間（ティック数）を加算する"""
        if duration < 0:
            raise ValueError(f"Duration cannot be negative: {duration}")
        return WorldTick(self.value + duration)

    def __add__(self, other: Any) -> "WorldTick":
        if isinstance(other, int):
            return self.add_duration(other)
        if isinstance(other, WorldTick):
            return self.add_duration(other.value)
        return NotImplemented

    def __sub__(self, other: "WorldTick") -> int:
        if not isinstance(other, WorldTick):
            return NotImplemented
        return self.value - other.value

    def __gt__(self, other: "WorldTick") -> bool:
        return self.value > other.value

    def __ge__(self, other: "WorldTick") -> bool:
        return self.value >= other.value

    def __lt__(self, other: "WorldTick") -> bool:
        return self.value < other.value

    def __le__(self, other: "WorldTick") -> bool:
        return self.value <= other.value

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"WorldTick({self.value})"
