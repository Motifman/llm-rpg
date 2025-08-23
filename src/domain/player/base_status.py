from dataclasses import dataclass


@dataclass(frozen=True)
class BaseStatus:
    """基礎ステータス"""
    attack: int
    defense: int
    speed: int
    critical_rate: float
    evasion_rate: float
    
    def __post_init__(self):
        if self.attack < 0:
            raise ValueError("attack must be greater than or equal to 0")
        if self.defense < 0:
            raise ValueError("defense must be greater than or equal to 0")
        if self.speed < 0:
            raise ValueError("speed must be greater than or equal to 0")
        if self.critical_rate < 0 or self.critical_rate > 1:
            raise ValueError("critical_rate must be between 0 and 1")
        if self.evasion_rate < 0 or self.evasion_rate > 1:
            raise ValueError("evasion_rate must be between 0 and 1")
    
    def __add__(self, other: 'BaseStatus') -> 'BaseStatus':
        if not isinstance(other, BaseStatus):
            raise TypeError(f"Invalid type: {type(other)}")
        return BaseStatus(
            attack=self.attack + other.attack,
            defense=self.defense + other.defense,
            speed=self.speed + other.speed,
            critical_rate=self.critical_rate + other.critical_rate,
            evasion_rate=self.evasion_rate + other.evasion_rate,
        )


EMPTY_STATUS = BaseStatus(0, 0, 0, 0.0, 0.0)