"""覚醒モード発動の server-side defaults。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AwakenedModeActivationDefaults:
    duration_ticks: int
    cooldown_reduction_rate: float
    mp_cost: int
    stamina_cost: int
    hp_cost: int


DEFAULT_AWAKENED_MODE_ACTIVATION = AwakenedModeActivationDefaults(
    duration_ticks=50,
    cooldown_reduction_rate=0.5,
    mp_cost=20,
    stamina_cost=30,
    hp_cost=0,
)
