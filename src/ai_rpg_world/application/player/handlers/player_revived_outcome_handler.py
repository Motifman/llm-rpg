"""PlayerRevivedEvent を受けて PlayerDeathGraceTimer から pending を消す (Issue #621)。

ダウン後の 30 tick 猶予中に revive されたとき、grace timer の pending state
を削除して DEAD 確定を回避する。pending でない player への呼び出しは
no-op (= 冪等)。
"""

from __future__ import annotations

import logging

from ai_rpg_world.application.common.exceptions import (
    ApplicationException,
    SystemErrorException,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent


class PlayerRevivedOutcomeHandler(EventHandler[PlayerRevivedEvent]):
    """PlayerRevivedEvent → PlayerDeathGraceTimer.cancel を呼ぶ。"""

    def __init__(self, *, grace_timer: PlayerDeathGraceTimer) -> None:
        if not isinstance(grace_timer, PlayerDeathGraceTimer):
            raise TypeError("grace_timer must be PlayerDeathGraceTimer")
        self._grace_timer = grace_timer
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: PlayerRevivedEvent) -> None:
        try:
            self._grace_timer.cancel(event.aggregate_id)
            self._logger.info(
                "Player %s revived (grace timer cancelled, hp_recovered=%d)",
                event.aggregate_id, event.hp_recovered,
            )
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in PlayerRevivedOutcomeHandler: %s", e
            )
            raise SystemErrorException(
                f"Player revived outcome handling failed: {e}",
                original_exception=e,
            ) from e
