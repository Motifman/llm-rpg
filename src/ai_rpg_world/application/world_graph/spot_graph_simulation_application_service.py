"""スポットグラフモード用のワールドティック（2D シミュレーションの軽量版）。"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import SpotGraphTravelStageService
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger, IReflectionRunner


class SpotGraphSimulationApplicationService:
    """スポットグラフ上のゲームループ（時間進行・継続移動・任意で LLM トリガ）。"""

    def __init__(
        self,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
        travel_stage: Optional[SpotGraphTravelStageService] = None,
        llm_turn_trigger: Optional["ILlmTurnTrigger"] = None,
        reflection_runner: Optional["IReflectionRunner"] = None,
    ) -> None:
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._travel_stage = travel_stage
        self._llm_turn_trigger = llm_turn_trigger
        self._reflection_runner = reflection_runner
        self._logger = logging.getLogger(self.__class__.__name__)

    def tick(self) -> WorldTick:
        """1 ティック進める（UoW 内で時間とスポット間移動を処理し、フックはトランザクション外）。"""
        with self._unit_of_work:
            current_tick = self._time_provider.advance_tick()
            if self._travel_stage is not None:
                self._travel_stage.run(current_tick)
        self._run_post_tick_hooks(current_tick)
        return current_tick

    def _run_post_tick_hooks(self, current_tick: WorldTick) -> None:
        if self._llm_turn_trigger is not None:
            self._llm_turn_trigger.run_scheduled_turns()
        if self._reflection_runner is not None:
            self._reflection_runner.run_after_tick(current_tick)


__all__ = ["SpotGraphSimulationApplicationService"]
