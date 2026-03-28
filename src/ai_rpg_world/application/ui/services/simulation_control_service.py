"""Simulation control service for UI-driven pause/resume/speed operations."""

from __future__ import annotations

from typing import Iterable, Optional

from ai_rpg_world.application.ui.contracts.interfaces import (
    IGameSceneEventBroker,
    ISimulationRuntimeControlPort,
)
from ai_rpg_world.application.ui.exceptions import SimulationSpeedValidationException
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection


class SimulationControlService:
    """Owns pause/resume/speed state exposed to the UI layer."""

    def __init__(
        self,
        projection: GameSceneProjection,
        broker: IGameSceneEventBroker,
        *,
        runtime_control: Optional[ISimulationRuntimeControlPort] = None,
    ) -> None:
        self._projection = projection
        self._broker = broker
        self._runtime_control = runtime_control

    def pause(self, *, spot_ids: Optional[Iterable[int]] = None) -> None:
        if self._runtime_control is not None:
            self._runtime_control.pause()
        for spot_id in self._resolve_spot_ids(spot_ids):
            self._broker.publish(
                self._projection.set_simulation_paused(spot_id=spot_id, is_paused=True)
            )

    def resume(self, *, spot_ids: Optional[Iterable[int]] = None) -> None:
        if self._runtime_control is not None:
            self._runtime_control.resume()
        for spot_id in self._resolve_spot_ids(spot_ids):
            self._broker.publish(
                self._projection.set_simulation_paused(spot_id=spot_id, is_paused=False)
            )

    def set_speed(
        self,
        *,
        speed_multiplier: float,
        spot_ids: Optional[Iterable[int]] = None,
    ) -> None:
        if speed_multiplier <= 0:
            raise SimulationSpeedValidationException(speed_multiplier)
        if self._runtime_control is not None:
            self._runtime_control.set_speed_multiplier(float(speed_multiplier))
        for spot_id in self._resolve_spot_ids(spot_ids):
            self._broker.publish(
                self._projection.set_simulation_speed(
                    spot_id=spot_id,
                    speed_multiplier=float(speed_multiplier),
                )
            )

    def _resolve_spot_ids(self, spot_ids: Optional[Iterable[int]]) -> list[int]:
        if spot_ids is not None:
            return list(spot_ids)
        return [snapshot.spot_id for snapshot in self._projection.list_snapshots()]

