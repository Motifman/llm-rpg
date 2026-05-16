"""スポットグラフモード用のワールドティック（2D シミュレーションの軽量版）。"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, TYPE_CHECKING

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
    from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
    from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
        HeartbeatObservationEmitter,
    )


class SpotGraphSimulationApplicationService:
    """スポットグラフ上のゲームループ（時間進行・継続移動・任意で LLM トリガ）。"""

    def __init__(
        self,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
        travel_stage: Optional[SpotGraphTravelStageService] = None,
        scenario_event_stage: Optional["_SpotGraphTickStage"] = None,
        reactive_binding_stage: Optional["_SpotGraphTickStage"] = None,
        reactive_object_state_stage: Optional["_SpotGraphTickStage"] = None,
        sync_action_resolver_stage: Optional["_SpotGraphTickStage"] = None,
        environment_stage: Optional["_SpotGraphTickStage"] = None,
        needs_decay_stage: Optional["_SpotGraphTickStage"] = None,
        llm_turn_trigger: Optional["ILlmTurnTrigger"] = None,
        heartbeat_emitter: Optional["HeartbeatObservationEmitter"] = None,
    ) -> None:
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._travel_stage = travel_stage
        self._scenario_event_stage = scenario_event_stage
        self._reactive_binding_stage = reactive_binding_stage
        self._reactive_object_state_stage = reactive_object_state_stage
        self._sync_action_resolver_stage = sync_action_resolver_stage
        self._environment_stage = environment_stage
        self._needs_decay_stage = needs_decay_stage
        self._llm_turn_trigger = llm_turn_trigger
        self._heartbeat_emitter = heartbeat_emitter
        self._logger = logging.getLogger(self.__class__.__name__)

    def tick(self) -> WorldTick:
        """1 ティック進める（UoW 内で時間とスポット間移動を処理し、フックはトランザクション外）。"""
        return self._execute_with_error_handling(
            operation=self._tick_impl,
            context={"action": "spot_graph_tick"},
        )

    def set_llm_turn_trigger(
        self, trigger: Optional["ILlmTurnTrigger"]
    ) -> None:
        """プレゼン層などから、ティック後に走らせる LLM トリガを差し替える（主に脱出デモ）。"""
        self._llm_turn_trigger = trigger

    def set_heartbeat_emitter(
        self, emitter: Optional["HeartbeatObservationEmitter"]
    ) -> None:
        """ティック後の heartbeat emitter を注入する（脱出デモなどプレゼン層から）。"""
        self._heartbeat_emitter = emitter

    def _tick_impl(self) -> WorldTick:
        with self._unit_of_work:
            current_tick = self._time_provider.advance_tick()
            if self._travel_stage is not None:
                self._travel_stage.run(current_tick)
            if self._scenario_event_stage is not None:
                self._scenario_event_stage.run(current_tick)
            if self._reactive_binding_stage is not None:
                # scenario_event の flag 更新を同 tick で反映するため、
                # scenario_event_stage の後に走らせる。
                self._reactive_binding_stage.run(current_tick)
            if self._reactive_object_state_stage is not None:
                # object 状態の reactive 評価。passage と同じく scenario_event
                # 後の flag/state を読みたいので reactive_binding_stage の後。
                self._reactive_object_state_stage.run(current_tick)
            if self._sync_action_resolver_stage is not None:
                # sync group の判定はその tick の prepare（ツール実行で
                # 既に flag 化されている）を見るため、reactive 反映の
                # 後で走らせる。完成 / タイムアウトに伴う on_complete /
                # on_timeout 効果は次ステージ以降に伝搬する。
                self._sync_action_resolver_stage.run(current_tick)
            if self._environment_stage is not None:
                self._environment_stage.run(current_tick)
            if self._needs_decay_stage is not None:
                self._needs_decay_stage.run(current_tick)
        self._run_post_tick_hooks(current_tick)
        return current_tick

    def _run_post_tick_hooks(self, current_tick: WorldTick) -> None:
        failures: list[tuple[str, Exception]] = []
        # 順序が重要: heartbeat → llm_turn_trigger。heartbeat が
        # ``schedules_turn=True`` の観測を enqueue した直後に turn trigger が
        # それを実行することで「idle tick でも NPC が動く」状態が成立する。
        hooks = (
            (
                "heartbeat_emitter",
                self._heartbeat_emitter,
                lambda hook: hook.run(current_tick),
            ),
            (
                "llm_turn_trigger",
                self._llm_turn_trigger,
                lambda hook: hook.run_scheduled_turns(),
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


class _SpotGraphTickStage(Protocol):
    def run(self, current_tick: WorldTick) -> None: ...
