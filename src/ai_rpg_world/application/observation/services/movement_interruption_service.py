"""
breaks_movement 観測時の経路キャンセルを担当するサービス。
LLM 制御プレイヤーのみ対象。movement_service の cancel_movement を呼び、
例外はログに記録して握りつぶす（観測蓄積の失敗にしない）。
"""

import logging
from typing import Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.llm.contracts.interfaces import ILLMPlayerResolver
from ai_rpg_world.application.world.contracts.commands import CancelMovementCommand
from ai_rpg_world.application.world.contracts.interfaces import ICancelMovementPort
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class MovementInterruptionService:
    """
    breaks_movement の観測に対して経路キャンセルを実行する。
    movement_service または llm_player_resolver が未設定の場合は何もしない。
    cancel_movement の例外は warning ログに記録して握りつぶす。
    """

    def __init__(
        self,
        movement_service: Optional[ICancelMovementPort] = None,
        llm_player_resolver: Optional[ILLMPlayerResolver] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._movement_service = movement_service
        self._llm_player_resolver = llm_player_resolver
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def maybe_cancel(self, player_id: PlayerId, output: ObservationOutput) -> None:
        """
        breaks_movement のときのみ、LLM 制御プレイヤーに対して経路キャンセルを実行する。
        条件を満たさない場合は no-op。
        cancel_movement が例外を投げた場合はログに記録して握りつぶす。
        """
        if not output.breaks_movement:
            return
        if self._movement_service is None:
            return
        if self._llm_player_resolver is None or not self._llm_player_resolver.is_llm_controlled(
            player_id
        ):
            return
        try:
            self._movement_service.cancel_movement(
                CancelMovementCommand(player_id=player_id.value)
            )
        except Exception as e:
            self._logger.warning(
                "Failed to cancel movement for player %s on breaks_movement: %s",
                player_id.value,
                str(e),
                exc_info=True,
            )
