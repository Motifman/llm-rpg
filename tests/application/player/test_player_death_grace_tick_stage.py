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
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestRun:
    """tick 毎の run(current_tick) で overdue を確定する。"""

    def test_grace_経過後の_player_が_DEAD_確定_する(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=0)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(current_tick=30)

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD

    def test_grace_未経過の_player_は_確定_しない(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(current_tick=20)  # 経過 10 tick (< 30)

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_確定後_grace_timer_からも_削除される(self) -> None:
        """DEAD 確定したら pending は不要なので clean up する (= 二重判定防止)。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=0)
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(current_tick=30)

        assert timer.is_pending(PlayerId(1)) is False

    def test_複数_player_を_独立に_判定(self) -> None:
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

        stage.run(current_tick=35)

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD
        assert reg.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.UNRESOLVED
        assert reg.get_outcome(PlayerId(3)) is PlayerOutcomeEnum.UNRESOLVED
        assert timer.is_pending(PlayerId(1)) is False
        assert timer.is_pending(PlayerId(2)) is True
        assert timer.is_pending(PlayerId(3)) is True

    def test_pending_が_空_でも_例外_なし(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        stage = PlayerDeathGraceTickStage(
            outcome_registry=reg,
            grace_timer=timer,
            grace_ticks=30,
        )

        stage.run(current_tick=100)  # no-op

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_既に_RESCUED_な_player_は_DEAD_に_上書きされない(self) -> None:
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

        stage.run(current_tick=30)

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
        # 既に resolved なので grace_timer の pending も掃除される
        assert timer.is_pending(PlayerId(1)) is False


class TestValidation:
    def test_outcome_registry_None_は_TypeError(self) -> None:
        with pytest.raises(TypeError):
            PlayerDeathGraceTickStage(
                outcome_registry=None,  # type: ignore[arg-type]
                grace_timer=PlayerDeathGraceTimer(),
                grace_ticks=30,
            )

    def test_grace_timer_None_は_TypeError(self) -> None:
        with pytest.raises(TypeError):
            PlayerDeathGraceTickStage(
                outcome_registry=PlayerOutcomeRegistry(),
                grace_timer=None,  # type: ignore[arg-type]
                grace_ticks=30,
            )

    def test_grace_ticks_非負(self) -> None:
        with pytest.raises(ValueError):
            PlayerDeathGraceTickStage(
                outcome_registry=PlayerOutcomeRegistry(),
                grace_timer=PlayerDeathGraceTimer(),
                grace_ticks=-1,
            )
