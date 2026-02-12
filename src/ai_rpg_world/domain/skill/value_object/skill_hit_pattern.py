from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.skill.enum.skill_enum import SkillHitPatternType
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillHitPatternValidationException
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class SkillHitTimelineSegment:
    start_offset_ticks: int
    duration_ticks: int
    shape: HitBoxShape
    velocity: HitBoxVelocity = HitBoxVelocity.zero()
    spawn_offset: Coordinate = Coordinate(0, 0, 0)
    segment_power_multiplier: float = 1.0

    def __post_init__(self):
        if self.start_offset_ticks < 0:
            raise SkillHitPatternValidationException(
                f"start_offset_ticks cannot be negative: {self.start_offset_ticks}"
            )
        if self.duration_ticks <= 0:
            raise SkillHitPatternValidationException(
                f"duration_ticks must be greater than 0: {self.duration_ticks}"
            )
        if self.segment_power_multiplier <= 0:
            raise SkillHitPatternValidationException(
                f"segment_power_multiplier must be greater than 0: {self.segment_power_multiplier}"
            )


@dataclass(frozen=True)
class SkillHitPattern:
    pattern_type: SkillHitPatternType
    timeline_segments: Tuple[SkillHitTimelineSegment, ...]

    def __post_init__(self):
        if not self.timeline_segments:
            raise SkillHitPatternValidationException("timeline_segments cannot be empty")

        previous_offset = -1
        for segment in self.timeline_segments:
            if segment.start_offset_ticks < previous_offset:
                raise SkillHitPatternValidationException(
                    "timeline_segments must be sorted by start_offset_ticks"
                )
            previous_offset = segment.start_offset_ticks

    @classmethod
    def single_pulse(
        cls,
        pattern_type: SkillHitPatternType,
        shape: HitBoxShape,
        duration_ticks: int = 1,
    ) -> "SkillHitPattern":
        return cls(
            pattern_type=pattern_type,
            timeline_segments=(SkillHitTimelineSegment(0, duration_ticks, shape),),
        )

    @classmethod
    def projectile(
        cls,
        shape: HitBoxShape,
        velocity: HitBoxVelocity,
        duration_ticks: int,
    ) -> "SkillHitPattern":
        return cls(
            pattern_type=SkillHitPatternType.PROJECTILE,
            timeline_segments=(
                SkillHitTimelineSegment(
                    0,
                    duration_ticks,
                    shape,
                    velocity=velocity,
                ),
            ),
        )

