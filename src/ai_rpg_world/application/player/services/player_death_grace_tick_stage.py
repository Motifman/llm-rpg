"""ダウン後 30 tick 経過した player を DEAD 確定する tick stage (Issue #621)。

PlayerDownedOutcomeHandler が pending 登録した player を tick 毎にスキャンし、
grace_ticks 経過した player を `outcome_registry.set_outcome(DEAD)` で確定する。

確定後は grace_timer から pending を削除して二重判定を防ぐ。既に他の経路で
RESCUED 等で resolved されていた player も同様に grace_timer から掃除する
(= 死体・生存問わず pending は不要)。

本番runtimeでは期限超過player一人を一つのcommandとして扱い、死亡結果、timer、
退場位置を一緒に確定する。後続playerの失敗で先行playerの確定は戻さない。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.player_status_tick_command_repository_provider import (
        PlayerStatusTickCommandRepositoryProviderPort,
    )


class PlayerDeathGraceTickStage:
    """grace_ticks 経過した pending player を DEAD 確定する。"""

    #: 倒れてから DEAD が確定するまでの既定の猶予 tick。
    #:
    #: **世界のほかの時間と突き合わせる必要がある値なので、呼び出し側に
    #: べた書きしない。** #864 のマージ後レビューで、会議の tick 上限が
    #: 偶然この値と一致しており、倒れている相手を報告すると会議のあいだに
    #: ちょうど死ぬ、という穴が見つかった。呼び出し側の数値リテラルだと
    #: 突き合わせようが無い。
    #:
    #: この猶予を短くするときは、会議の上限 (GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT)
    #: との関係を壊していないか確認すること。関係は
    #: tests/application/world_graph/test_meeting_does_not_outlive_rescue.py
    #: が固定している。
    DEFAULT_GRACE_TICKS = 30

    def __init__(
        self,
        *,
        outcome_registry: PlayerOutcomeRegistry,
        grace_timer: PlayerDeathGraceTimer,
        grace_ticks: int,
        fallen_body_registry: FallenBodyRegistry | None = None,
        departed_position_store: DepartedPositionStore | None = None,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        if not isinstance(outcome_registry, PlayerOutcomeRegistry):
            raise TypeError("outcome_registry must be PlayerOutcomeRegistry")
        if not isinstance(grace_timer, PlayerDeathGraceTimer):
            raise TypeError("grace_timer must be PlayerDeathGraceTimer")
        if not isinstance(grace_ticks, int) or grace_ticks < 0:
            raise ValueError(
                f"grace_ticks must be non-negative int, got {grace_ticks!r}"
            )
        if fallen_body_registry is not None and not isinstance(
            fallen_body_registry,
            FallenBodyRegistry,
        ):
            raise TypeError("fallen_body_registry must be FallenBodyRegistry")
        if departed_position_store is not None and not isinstance(
            departed_position_store,
            DepartedPositionStore,
        ):
            raise TypeError(
                "departed_position_store must be DepartedPositionStore"
            )
        if (fallen_body_registry is None) != (departed_position_store is None):
            raise ValueError(
                "fallen_body_registry and departed_position_store must be "
                "configured together"
            )
        self._outcome_registry = outcome_registry
        self._grace_timer = grace_timer
        self._grace_ticks = grace_ticks
        self._fallen_body_registry = fallen_body_registry
        self._departed_position_store = departed_position_store
        self._command_scope_factory = command_scope_factory
        self._logger = logging.getLogger(self.__class__.__name__)
        if command_scope_factory is not None:
            self._require_scope_dependencies()

    def set_command_scope_factory(
        self,
        factory: (
            "CommandScopeFactoryPort["
            "PlayerStatusTickCommandRepositoryProviderPort]"
        ),
    ) -> None:
        """本番stageを期限超過player一人単位の確定境界へ接続する。"""
        self._require_scope_dependencies()
        self._command_scope_factory = factory

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
            if self._command_scope_factory is not None:
                self._run_player_command(player_id, tick_value)
                continue
            self._run_legacy(player_id, tick_value)

    def _run_legacy(self, player_id: PlayerId, tick_value: int) -> None:
        """直接構築入口では従来のcallback順序を維持する。"""
        # set_outcome は冪等なので、既に RESCUED 等で resolved な player は
        # DEAD に塗り直されない。それでも pending は掃除する (= 不要)。
        changed = self._outcome_registry.set_outcome(
            player_id, PlayerOutcomeEnum.DEAD
        )
        self._grace_timer.cancel(player_id)
        self._log_committed(player_id, tick_value, changed)

    def _run_player_command(self, player_id: PlayerId, tick_value: int) -> None:
        """playerのDEAD・pending削除・退場位置を一緒に確定する。"""
        changed = False
        old_outcome = self._outcome_registry.get_outcome(player_id)
        missing_body = False
        try:
            with self._command_scope_factory.create() as scope:
                # 期限超過一覧の取得後、scope待機中に蘇生される可能性がある。
                # 資源所有権を得た後にpendingと正本statusを再確認する。
                if not self._grace_timer.is_overdue(
                    player_id,
                    current_tick=tick_value,
                    grace_ticks=self._grace_ticks,
                ):
                    return
                status = scope.repositories.player_statuses.find_by_id(player_id)
                if status is None:
                    raise RuntimeError(
                        "death grace player status is missing: "
                        f"player_id={int(player_id)}"
                    )
                if not status.is_down:
                    # PlayerRevivedEventの個別handler失敗でtimer/bodyだけ残った場合も、
                    # 生存状態を正本として古い猶予状態を修復する。
                    self._fallen_body_registry.remove(player_id)
                    self._grace_timer.cancel(player_id)
                    return
                old_outcome = self._outcome_registry.get_outcome(player_id)
                changed = self._outcome_registry.set_outcome(
                    player_id,
                    PlayerOutcomeEnum.DEAD,
                    notify_callbacks=False,
                )
                if changed:
                    body = self._fallen_body_registry.find(player_id)
                    if body is None:
                        missing_body = True
                    else:
                        self._departed_position_store.place(
                            player_id,
                            body.spot_id,
                        )
                self._grace_timer.cancel(player_id)
        except CommandPostCommitException:
            self._notify_committed(
                player_id,
                old_outcome,
                tick_value,
                changed=changed,
                missing_body=missing_body,
            )
            raise
        self._notify_committed(
            player_id,
            old_outcome,
            tick_value,
            changed=changed,
            missing_body=missing_body,
        )

    def _notify_committed(
        self,
        player_id: PlayerId,
        old_outcome: PlayerOutcomeEnum,
        tick_value: int,
        *,
        changed: bool,
        missing_body: bool,
    ) -> None:
        """確定した状態にだけ警告・outcome callback・成功ログを追随させる。"""
        if missing_body:
            self._logger.warning(
                "DEAD outcome has no fallen-body record; departed position "
                "was not initialized: player_id=%s",
                int(player_id),
            )
        if changed:
            self._outcome_registry.notify_outcome_change(
                player_id,
                old_outcome,
                PlayerOutcomeEnum.DEAD,
            )
        self._log_committed(player_id, tick_value, changed)

    def _log_committed(
        self,
        player_id: PlayerId,
        tick_value: int,
        changed: bool,
    ) -> None:
        """commit済みの死亡確定またはpending掃除だけを記録する。"""
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

    def _require_scope_dependencies(self) -> None:
        """scope経路に必要な退場状態の配線漏れを開始前に止める。"""
        if (
            self._fallen_body_registry is None
            or self._departed_position_store is None
        ):
            raise RuntimeError(
                "death grace CommandScope requires fallen body and departed "
                "position stores"
            )
