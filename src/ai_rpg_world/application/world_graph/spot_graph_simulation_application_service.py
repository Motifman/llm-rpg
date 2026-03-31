"""スポットグラフモード用のワールドティック（2D シミュレーションの軽量版）。"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world_graph.exceptions import (
    SpotGraphPostTickHookFailedException,
    SpotGraphSimulationException,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import SpotGraphTravelStageService
from ai_rpg_world.domain.common.exception import DomainException
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
        return self._execute_with_error_handling(
            operation=self._tick_impl,
            context={"action": "spot_graph_tick"},
        )

    def _tick_impl(self) -> WorldTick:
        with self._unit_of_work:
            current_tick = self._time_provider.advance_tick()
            if self._travel_stage is not None:
                self._travel_stage.run(current_tick)
        self._run_post_tick_hooks(current_tick)
        return current_tick

    def _run_post_tick_hooks(self, current_tick: WorldTick) -> None:
        failures: list[tuple[str, Exception]] = []
        hooks = (
            ("llm_turn_trigger", self._llm_turn_trigger, lambda hook: hook.run_scheduled_turns()),
            (
                "reflection_runner",
                self._reflection_runner,
                lambda hook: hook.run_after_tick(current_tick),
            ),
        )
        for hook_name, hook, runner in hooks:
            if hook is None:
                continue
            try:
                runner(hook)
            except Exception as exc:  # post-commit hook なので残りも実行して失敗を集約する
                self._logger.exception(
                    "Spot graph post-tick hook failed",
                    extra={"hook_name": hook_name, "tick": current_tick.value},
                )
                failures.append((hook_name, exc))
        if failures:
            raise SpotGraphPostTickHookFailedException(
                current_tick=current_tick,
                failed_hooks=tuple(name for name, _ in failures),
                original_exception=failures[0][1],
            )

    def _execute_with_error_handling(self, operation, context: dict) -> WorldTick:
        try:
            return operation()
        except ApplicationException:
            raise
        except DomainException as exc:
            raise SpotGraphSimulationException(str(exc), cause=exc, **context) from exc
        except Exception as exc:
            self._logger.error(
                "Unexpected error in spot graph simulation",
                extra={**context, "error": str(exc)},
            )
            raise SystemErrorException(
                f"{context.get('action', 'spot_graph_tick')} failed: {str(exc)}",
                original_exception=exc,
            ) from exc


__all__ = ["SpotGraphSimulationApplicationService"]
