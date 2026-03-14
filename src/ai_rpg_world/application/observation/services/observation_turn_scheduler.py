"""schedules_turn 観測時の LLM ターンスケジュール呼び出しを担うサービス"""

from typing import Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
    ILlmTurnTrigger,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ObservationTurnScheduler:
    """
    schedules_turn の観測時にのみ schedule_turn を呼ぶ。
    turn_trigger または llm_player_resolver が未設定の場合は何もしない。
    非 LLM 制御プレイヤーには schedule_turn を呼ばない。
    """

    def __init__(
        self,
        turn_trigger: Optional[ILlmTurnTrigger] = None,
        llm_player_resolver: Optional[ILLMPlayerResolver] = None,
    ) -> None:
        self._turn_trigger = turn_trigger
        self._llm_player_resolver = llm_player_resolver

    def maybe_schedule(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
    ) -> None:
        """
        schedules_turn のときのみ LLM ターンを積む。
        breaks_movement では呼ばない（MovementInterruptionService の責務と分離）。
        """
        if not output.schedules_turn:
            return
        if self._turn_trigger is None or self._llm_player_resolver is None:
            return
        if not self._llm_player_resolver.is_llm_controlled(player_id):
            return
        self._turn_trigger.schedule_turn(player_id)
