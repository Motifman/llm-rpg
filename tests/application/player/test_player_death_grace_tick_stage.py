"""PlayerDeathGraceTickStage の挙動検証 (Issue #621)。

tick 駆動で PlayerDeathGraceTimer をスキャンし、猶予 30 tick を過ぎた
player を PlayerOutcomeRegistry の DEAD に確定させる stage service。

PlayerDownedOutcomeHandler が pending 登録した player を、grace_ticks
後に「もう手遅れ」として確定する経路。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.player.services.player_death_grace_tick_stage import (
    PlayerDeathGraceTickStage,
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


class TestRun:
    """tick 毎の run(current_tick) で overdue を確定する。

    ``SpotGraphSimulationApplicationService`` (実 run で使われる呼び出し元)
    は ``_SpotGraphTickStage`` protocol に従い ``WorldTick`` を渡す。#710 で
    ``PlayerDownedOutcomeHandler`` の登録が動くようになるまで ``run()`` は
    pending が常に空のまま呼ばれ続けていたため、この型不一致
    (``WorldTick - int`` の ``TypeError``) は実 run r1_001 で初めて down が
    発生するまで一度も踏まれなかった。ここでは全テストが ``WorldTick`` を
    渡す実経路の型で固定する。
    """

    def test_grace_after_player_dead(self) -> None:
        """grace 経過後の player が DEAD 確定 する。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=0)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(WorldTick(30))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD

    def test_grace_player(self) -> None:
        """grace 未経過の player は確定しない。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(WorldTick(20))  # 経過 10 tick (< 30)

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_after_grace_timer_deleted(self) -> None:
        """DEAD 確定したら pending は不要なので clean up する (= 二重判定防止)。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=0)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(WorldTick(30))

        assert timer.is_pending(PlayerId(1)) is False

    def test_multiple_player_independently(self) -> None:
        """複数 player を独立に判定。"""
        reg = PlayerOutcomeRegistry.new_for_players(
            [PlayerId(1), PlayerId(2), PlayerId(3)]
        )
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=0)   # tick 30 で overdue
        timer.register(PlayerId(2), downed_at_tick=10)  # tick 40 で overdue
        timer.register(PlayerId(3), downed_at_tick=20)  # tick 50 で overdue
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(WorldTick(35))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD
        assert reg.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.UNRESOLVED
        assert reg.get_outcome(PlayerId(3)) is PlayerOutcomeEnum.UNRESOLVED
        assert timer.is_pending(PlayerId(1)) is False
        assert timer.is_pending(PlayerId(2)) is True
        assert timer.is_pending(PlayerId(3)) is True

    def test_pending_empty_raises_exception(self) -> None:
        """pending が空でも例外なし。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(WorldTick(100))  # no-op

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_rescued_player_dead(self) -> None:
        """grace pending 中に scenario_event で RESCUED 確定されたら、
        set_outcome が冪等なので DEAD に塗り直されない (= 旧仕様の冪等性保証)。
        """
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=0)
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(WorldTick(30))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
        # 既に resolved なので grace_timer の pending も掃除される
        assert timer.is_pending(PlayerId(1)) is False

    def test_world_tick_raises_type_error(self) -> None:
        """実 run r1_001 の再現ケース (裏取り済みのクラッシュ)。

        ``SpotGraphSimulationApplicationService._tick_impl`` は
        ``self._time_provider.advance_tick()`` が返す ``WorldTick`` を
        そのまま ``death_grace_stage.run(current_tick)`` に渡す。
        修正前はこの WorldTick が ``PlayerDeathGraceTimer.overdue_players``
        まで生で渡り、``WorldTick - int`` の減算で
        ``TypeError: unsupported operand type(s) for -: 'WorldTick' and 'int'``
        になり tick 全体が SystemErrorException で停止していた。
        """
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=5)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        # クラッシュしないこと自体が確認事項 (例外が飛べば pytest が失敗させる)
        stage.run(WorldTick(35))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD


class TestValidation:
    def test_outcome_registry_none_raises_type_error(self) -> None:
        """outcome registry None は TypeError。"""
        with pytest.raises(TypeError):
            PlayerDeathGraceTickStage(
                outcome_registry=None,  # type: ignore[arg-type]
                grace_timer=PlayerDeathGraceTimer(),
                grace_ticks=30,
            )

    def test_grace_timer_none_raises_type_error(self) -> None:
        """grace timer None は TypeError。"""
        with pytest.raises(TypeError):
            PlayerDeathGraceTickStage(
                outcome_registry=PlayerOutcomeRegistry(),
                grace_timer=None,  # type: ignore[arg-type]
                grace_ticks=30,
            )

    def test_grace_ticks_non(self) -> None:
        """grace ticks 非負。"""
        with pytest.raises(ValueError):
            PlayerDeathGraceTickStage(
                outcome_registry=PlayerOutcomeRegistry(),
                grace_timer=PlayerDeathGraceTimer(),
                grace_ticks=-1,
            )
