"""PlayerDownedEvent を受けて outcome を DEAD に確定する (Phase E-3)。

HP が 0 になった瞬間に PlayerStatusAggregate が PlayerDownedEvent を出す。
このハンドラはその event を購読し、PlayerOutcomeRegistry の該当エントリを
DEAD に確定させる。

設計 §6: 「player.outcome = DEAD: HP 0 になる (空腹・寒さ・モンスター・
接触ダメージ等)」 を実装する第一の経路。RESCUED / STRANDED の確定経路は
別ハンドラ (rescue 観測 / tick 上限) で実装する。
"""

from __future__ import annotations

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)


class PlayerDownedOutcomeHandler(EventHandler[PlayerDownedEvent]):
    """PlayerDownedEvent → PlayerOutcomeRegistry を DEAD に更新する。

    `set_outcome` は冪等的なので、既に RESCUED 等で確定済みのプレイヤーが
    後から HP 0 (= ゾンビ event) になっても上書きされない。これは
    「救助された直後に何らかのバグで HP が 0 になっても、死亡として
    塗り直されない」という挙動を保証する。
    """

    def __init__(self, outcome_registry: PlayerOutcomeRegistry) -> None:
        self._outcome_registry = outcome_registry
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
        changed = self._outcome_registry.set_outcome(
            player_id, PlayerOutcomeEnum.DEAD,
        )
        if changed:
            self._logger.info(
                "Player %s outcome set to DEAD (killer=%s)",
                player_id, event.killer_player_id,
            )
        else:
            # 既に resolved (RESCUED 等) なケース。warning でも error でもなく
            # informational に留める。
            self._logger.debug(
                "Player %s already resolved as %s, ignoring DEAD transition",
                player_id, self._outcome_registry.get_outcome(player_id),
            )
