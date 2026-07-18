"""ダウン後 30 tick 経過した player を DEAD 確定する tick stage (Issue #621)。

PlayerDownedOutcomeHandler が pending 登録した player を tick 毎にスキャンし、
grace_ticks 経過した player を `outcome_registry.set_outcome(DEAD)` で確定する。

確定後は grace_timer から pending を削除して二重判定を防ぐ。既に他の経路で
RESCUED 等で resolved されていた player も同様に grace_timer から掃除する
(= 死体・生存問わず pending は不要)。

設計上の position:
- world_runtime の post-tick hooks の 1 つとして組み込まれる予定
- 同型 stage: `SpotGraphNeedsDecayStageService`, `SpotGraphLifecycleStage`,
  `HeartbeatObservationEmitter` 等
"""

from __future__ import annotations

import logging

from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)


class PlayerDeathGraceTickStage:
    """grace_ticks 経過した pending player を DEAD 確定する。"""

    def __init__(
        self,
        *,
        outcome_registry: PlayerOutcomeRegistry,
        grace_timer: PlayerDeathGraceTimer,
        grace_ticks: int,
    ) -> None:
        if not isinstance(outcome_registry, PlayerOutcomeRegistry):
            raise TypeError("outcome_registry must be PlayerOutcomeRegistry")
        if not isinstance(grace_timer, PlayerDeathGraceTimer):
            raise TypeError("grace_timer must be PlayerDeathGraceTimer")
        if not isinstance(grace_ticks, int) or grace_ticks < 0:
            raise ValueError(
                f"grace_ticks must be non-negative int, got {grace_ticks!r}"
            )
        self._outcome_registry = outcome_registry
        self._grace_timer = grace_timer
        self._grace_ticks = grace_ticks
        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self, current_tick: WorldTick) -> None:
        """tick 毎に呼ばれる。overdue player を DEAD 確定して pending 掃除する。

        呼び出し元 (``SpotGraphSimulationApplicationService``) は他の
        tick stage 同様 ``WorldTick`` を渡す (`_SpotGraphTickStage` protocol
        参照)。``PlayerDeathGraceTimer.overdue_players`` は int を期待するため、
        stage の入口 (= application 層の境界) で ``.value`` に変換する。
        ここを怠ると ``WorldTick - int`` の減算で ``TypeError`` になる
        (実 run r1_001 で発生したクラッシュ、#710 で register が動くように
        なって初めて露出した潜在バグ)。
        """
        tick_value = current_tick.value
        overdue = self._grace_timer.overdue_players(
            current_tick=tick_value,
            grace_ticks=self._grace_ticks,
        )
        for player_id in overdue:
            # set_outcome は冪等なので、既に RESCUED 等で resolved な player は
            # DEAD に塗り直されない。それでも pending は掃除する (= 不要)。
            changed = self._outcome_registry.set_outcome(
                player_id, PlayerOutcomeEnum.DEAD
            )
            self._grace_timer.cancel(player_id)
            if changed:
                self._logger.info(
                    "Player %s outcome confirmed as DEAD after grace period (tick=%d)",
                    player_id, tick_value,
                )
            else:
                self._logger.debug(
                    "Player %s already resolved as %s, cleared grace pending only",
                    player_id, self._outcome_registry.get_outcome(player_id),
                )
