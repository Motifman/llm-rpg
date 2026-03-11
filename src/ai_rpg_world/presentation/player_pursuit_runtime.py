"""Player pursuit-capable runtime composition entrypoint.

This module provides the authoritative non-test assembly seam for a player
runtime that must expose both pursuit tool wiring and pursuit continuation in
the same composed package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

from ai_rpg_world.application.llm.bootstrap import ComposeLlmRuntimeResult
from ai_rpg_world.application.llm.wiring import (
    LlmAgentWiringResult,
    create_llm_agent_wiring,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.contracts.interfaces import (
        IReflectionRunner,
        ILlmTurnTrigger,
    )
    from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
        ObservationEventHandlerRegistry,
    )


class PlayerPursuitRuntimeResult:
    """Composed runtime package for pursuit-capable player flows."""

    def __init__(
        self,
        *,
        wiring_result: LlmAgentWiringResult,
        pursuit_command_service: Any,
        pursuit_continuation_service: Any,
        event_handler_composition: Optional[Any] = None,
        world_simulation_service: Optional[Any] = None,
    ) -> None:
        self.wiring_result = wiring_result
        self.pursuit_command_service = pursuit_command_service
        self.pursuit_continuation_service = pursuit_continuation_service
        self.event_handler_composition = event_handler_composition
        self.world_simulation_service = world_simulation_service

    @property
    def observation_registry(self) -> "ObservationEventHandlerRegistry":
        return self.wiring_result.observation_registry

    @property
    def llm_turn_trigger(self) -> "ILlmTurnTrigger":
        return self.wiring_result.llm_turn_trigger

    @property
    def reflection_runner(self) -> Optional["IReflectionRunner"]:
        return self.wiring_result.reflection_runner

    @property
    def pursuit_enabled(self) -> bool:
        return (
            self.pursuit_command_service is not None
            and self.pursuit_continuation_service is not None
        )

    def assert_pursuit_enabled(self) -> None:
        """Fail fast if the assembled runtime drifted into a half-wired state."""
        if self.pursuit_command_service is None:
            raise TypeError("pursuit_command_service must not be None")
        if self.pursuit_continuation_service is None:
            raise TypeError("pursuit_continuation_service must not be None")
        if self.world_simulation_service is not None and (
            getattr(self.world_simulation_service, "_pursuit_continuation_service", None)
            is None
        ):
            raise ValueError(
                "world_simulation_service must carry pursuit_continuation_service"
            )
        if self.event_handler_composition is not None and (
            getattr(self.event_handler_composition, "_observation_registry", None) is None
        ):
            raise ValueError(
                "event_handler_composition must carry observation_registry"
            )

    @classmethod
    def from_compose_result(
        cls,
        compose_result: ComposeLlmRuntimeResult,
        *,
        pursuit_command_service: Any,
        pursuit_continuation_service: Any,
    ) -> "PlayerPursuitRuntimeResult":
        return cls(
            wiring_result=compose_result.wiring_result,
            event_handler_composition=compose_result.event_handler_composition,
            world_simulation_service=compose_result.world_simulation_service,
            pursuit_command_service=pursuit_command_service,
            pursuit_continuation_service=pursuit_continuation_service,
        )


def compose_player_pursuit_runtime(
    *,
    pursuit_command_service: Any,
    pursuit_continuation_service: Any,
    composition_builder: Optional[
        Callable[["ObservationEventHandlerRegistry"], Any]
    ] = None,
    service_builder: Optional[
        Callable[[Any, "ILlmTurnTrigger", Optional["IReflectionRunner"]], Any]
    ] = None,
    **wiring_kwargs: Any,
) -> PlayerPursuitRuntimeResult:
    """Compose a runtime package that explicitly includes both pursuit seams.

    The generic `create_llm_agent_wiring(...)` helper remains low-level and keeps
    pursuit tooling optional. This entrypoint defines the higher-level contract
    used by player pursuit runtime callers: command-path wiring and world-tick
    continuation must be assembled together or the composition fails.
    """

    if pursuit_command_service is None:
        raise TypeError("pursuit_command_service must not be None")
    if pursuit_continuation_service is None:
        raise TypeError("pursuit_continuation_service must not be None")

    wiring_result = create_llm_agent_wiring(
        pursuit_command_service=pursuit_command_service,
        **wiring_kwargs,
    )
    composition = None
    if composition_builder is not None:
        composition = composition_builder(wiring_result.observation_registry)

    service = None
    if service_builder is not None:
        service = service_builder(
            pursuit_continuation_service,
            wiring_result.llm_turn_trigger,
            wiring_result.reflection_runner,
        )

    result = PlayerPursuitRuntimeResult(
        wiring_result=wiring_result,
        event_handler_composition=composition,
        world_simulation_service=service,
        pursuit_command_service=pursuit_command_service,
        pursuit_continuation_service=pursuit_continuation_service,
    )
    result.assert_pursuit_enabled()
    return result


__all__ = [
    "PlayerPursuitRuntimeResult",
    "compose_player_pursuit_runtime",
]
