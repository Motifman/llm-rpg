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
        assert self.attack > 0, "attack must be greater than 0"
        assert self.defense > 0, "defense must be greater than 0"
        assert self.speed > 0, "speed must be greater than 0"
        assert self.critical_rate >= 0 and self.critical_rate <= 1, "critical_rate must be between 0 and 1"
        assert self.evasion_rate >= 0 and self.evasion_rate <= 1, "evasion_rate must be between 0 and 1"