from dataclasses import dataclass
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class HitBoxSpawnParam:
    """HitBox生成に必要なパラメータセット"""
    shape: HitBoxShape
    velocity: HitBoxVelocity
    initial_coordinate: Coordinate
    activation_tick: int
    duration_ticks: int
    power_multiplier: float
    attacker_stats: BaseStats | None = None
