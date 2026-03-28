"""UI-facing ports."""

from abc import ABC, abstractmethod

from ai_rpg_world.application.ui.contracts.dtos import GameSceneDeltaEventDto
from ai_rpg_world.application.world.contracts.commands import MoveTileCommand


class IGameSceneEventBroker(ABC):
    """Publishes UI-facing delta events to a transport-specific sink."""

    @abstractmethod
    def publish(self, event: GameSceneDeltaEventDto) -> None:
        """Publish a single scene delta event."""
        pass

    @abstractmethod
    def get_published_events(
        self, *, scene_id: str | None = None
    ) -> list[GameSceneDeltaEventDto]:
        """Return published events, optionally filtered by scene_id."""
        pass


class IManualMovementPort(ABC):
    """Port for single-step manual movement."""

    @abstractmethod
    def move_tile(self, command: MoveTileCommand):
        """Execute one tile movement step."""
        pass


class ISimulationRuntimeControlPort(ABC):
    """Optional port that can propagate control state into the runtime loop."""

    @abstractmethod
    def pause(self) -> None:
        pass

    @abstractmethod
    def resume(self) -> None:
        pass

    @abstractmethod
    def set_speed_multiplier(self, speed_multiplier: float) -> None:
        pass
