"""PlayerDownedEvent を受けて DEAD 確定までの猶予タイマーに登録する (Issue #621)。

旧仕様 (Phase E-3 〜 Issue #621 まで): HP 0 で即時 set_outcome(DEAD)。
新仕様 (Issue #621 以降): HP 0 で grace_timer.register を呼び、30 tick の
猶予を設ける。その間に first_aid / tend_to_player で revive されれば
DEAD 確定を回避できる。

責務:
- 既に RESCUED 等で確定済みの player に対する後発 event は無視 (= 旧仕様の
  冪等性を保つ)
- それ以外は grace_timer に (player_id, current_tick) を登録
- 実際の DEAD 確定は PlayerDeathGraceTickStage が tick 毎にスキャンして行う
"""

from __future__ import annotations

import logging
from typing import Callable

from ai_rpg_world.application.common.exceptions import (
    ApplicationException,
    SystemErrorException,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)


class PlayerDownedOutcomeHandler(EventHandler[PlayerDownedEvent]):
    """PlayerDownedEvent → PlayerDeathGraceTimer に pending 登録する。

    既に RESCUED 等で resolved 済みの player は登録しない (= 冪等)。
    """

    def __init__(
        self,
        *,
        outcome_registry: PlayerOutcomeRegistry,
        grace_timer: PlayerDeathGraceTimer,
        current_tick_provider: Callable[[], int],
    ) -> None:
        if not isinstance(outcome_registry, PlayerOutcomeRegistry):
            raise TypeError("outcome_registry must be PlayerOutcomeRegistry")
        if not isinstance(grace_timer, PlayerDeathGraceTimer):
            raise TypeError("grace_timer must be PlayerDeathGraceTimer")
        if not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable")
        self._outcome_registry = outcome_registry
        self._grace_timer = grace_timer
        self._current_tick_provider = current_tick_provider
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: PlayerDownedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in PlayerDownedOutcomeHandler: %s", e
            )
            raise SystemErrorException(
                f"Player downed outcome handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: PlayerDownedEvent) -> None:
        player_id = event.aggregate_id
        # 既に resolved (RESCUED 等) なら pending 登録もしない (= 冪等)
        if self._outcome_registry.get_outcome(player_id).is_resolved:
            self._logger.debug(
                "Player %s already resolved as %s, skipping grace registration",
                player_id,
                self._outcome_registry.get_outcome(player_id),
            )
            return
        current_tick = int(self._current_tick_provider())
        self._grace_timer.register(player_id, downed_at_tick=current_tick)
        self._logger.info(
            "Player %s downed at tick %d (grace timer started, killer=%s)",
            player_id, current_tick, event.killer_player_id,
        )
