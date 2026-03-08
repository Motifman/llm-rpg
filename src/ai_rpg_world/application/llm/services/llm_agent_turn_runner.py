"""
LLM エージェントの 1 ターン実行ランナー。

即時停止（breaks_movement）は ObservationEventHandler で行う。
本ランナーは schedule_turn により呼ばれ、オーケストレータ経由で通常の run_turn のみ実行する。
"""

import logging
from typing import Any, Callable

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import IActionResultStore
from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.application.world.exceptions.base_exception import (
    WorldApplicationException,
    WorldSystemErrorException,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class LlmAgentTurnRunner:
    """
    スケジュール済みプレイヤーについて run_turn を実行する。
    即時停止（breaks_movement）は ObservationEventHandler 側で movement_service.cancel_movement により行われる。
    """

    def __init__(
        self,
        observation_buffer: IObservationContextBuffer,
        world_query_service: Any,
        movement_service: Any,
        action_result_store: IActionResultStore,
        orchestrator: LlmAgentOrchestrator,
    ) -> None:
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not callable(getattr(world_query_service, "get_player_current_state", None)):
            raise TypeError("world_query_service must have get_player_current_state")
        if not callable(getattr(movement_service, "cancel_movement", None)):
            raise TypeError("movement_service must have cancel_movement")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if not isinstance(orchestrator, LlmAgentOrchestrator):
            raise TypeError("orchestrator must be LlmAgentOrchestrator")
        self._observation_buffer = observation_buffer
        self._world_query_service = world_query_service
        self._movement_service = movement_service
        self._action_result_store = action_result_store
        self._orchestrator = orchestrator
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self, operation: Callable[[], LlmCommandResultDto], context: dict
    ) -> LlmCommandResultDto:
        """共通の例外処理。WorldApplicationException はそのまま、それ以外の例外は WorldSystemErrorException に包む。"""
        try:
            return operation()
        except WorldApplicationException:
            raise
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        """
        1 ターン実行する。即時停止は ObservationEventHandler 側で行われている。
        戻り値はオーケストレータの run_turn と同じ LlmCommandResultDto。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")

        return self._execute_with_error_handling(
            operation=lambda: self._run_turn_impl(player_id),
            context={"action": "run_turn", "player_id": player_id.value},
        )

    def _run_turn_impl(self, player_id: PlayerId) -> LlmCommandResultDto:
        """run_turn の実装。オーケストレータを実行する。即時停止は ObservationEventHandler 側で済んでいる。"""
        return self._orchestrator.run_turn(player_id)
