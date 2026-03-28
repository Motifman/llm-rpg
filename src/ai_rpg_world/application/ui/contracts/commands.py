"""Command DTOs for UI-side control actions."""

from dataclasses import dataclass

from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


@dataclass(frozen=True)
class PauseSimulationCommand:
    scene_id: str | None = None


@dataclass(frozen=True)
class ResumeSimulationCommand:
    scene_id: str | None = None


@dataclass(frozen=True)
class SetSimulationSpeedCommand:
    speed_multiplier: float
    scene_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.speed_multiplier, (int, float)):
            raise TypeError("speed_multiplier must be float-like")
        if float(self.speed_multiplier) <= 0:
            raise ValueError("speed_multiplier must be greater than 0")


@dataclass(frozen=True)
class MoveManualActorCommand:
    player_id: int
    direction: DirectionEnum

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if not isinstance(self.direction, DirectionEnum):
            raise TypeError("direction must be DirectionEnum")

