"""PlayerDownedOutcomeHandler の挙動検証。

Issue #621 で仕様変更:
- 旧: PlayerDownedEvent → 即時 set_outcome(DEAD)
- 新: PlayerDownedEvent → grace_timer.register(player_id, current_tick)
       (= 30 tick 猶予中。tick stage が経過判定して DEAD 確定する)

handler が直接 outcome_registry を触らなくなったため、registry は
復活確認用 (= RESCUED 等で既に resolved な player は pending 登録もしない)
の依存として残す。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.player.handlers.player_downed_outcome_handler import (
    PlayerDownedOutcomeHandler,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_downed_event(player_id: int) -> PlayerDownedEvent:
    return PlayerDownedEvent.create(
        aggregate_id=PlayerId(player_id),
        aggregate_type="PlayerStatusAggregate",
        killer_player_id=None,
    )


def _make_handler(
    *,
    reg: PlayerOutcomeRegistry,
    timer: PlayerDeathGraceTimer,
    tick: int = 0,
) -> PlayerDownedOutcomeHandler:
    return PlayerDownedOutcomeHandler(
        outcome_registry=reg,
        grace_timer=timer,
        current_tick_provider=lambda: tick,
    )


class TestPendingRegistration:
    """ダウン event 受信で grace_timer に pending 登録される (Issue #621 新仕様)。"""

    def test_player_downed_event_grace_timer_register(self) -> None:
        """PlayerDownedEvent 受信で grace timer に register される。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        handler = _make_handler(reg=reg, timer=timer, tick=42)

        handler.handle(_make_downed_event(1))

        assert timer.is_pending(PlayerId(1)) is True
        # 引数で渡した tick が起点として登録されている
        overdue = timer.overdue_players(current_tick=42 + 30, grace_ticks=30)
        assert PlayerId(1) in overdue
        overdue_before = timer.overdue_players(
            current_tick=42 + 29, grace_ticks=30
        )
        assert PlayerId(1) not in overdue_before

    def test_player_downed_event_outcome_dead(self) -> None:
        """旧仕様の即時 DEAD ではなく、UNRESOLVED のまま pending 登録のみ。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        handler = _make_handler(reg=reg, timer=timer, tick=10)

        handler.handle(_make_downed_event(1))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_rescued_player_pending(self) -> None:
        """救助確定済みの player に対する後発 PlayerDownedEvent は無視。
        旧仕様で「冪等で no-op」だった部分の新仕様での同等保証。
        """
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        timer = PlayerDeathGraceTimer()
        handler = _make_handler(reg=reg, timer=timer, tick=10)

        handler.handle(_make_downed_event(1))

        assert timer.is_pending(PlayerId(1)) is False
        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED

    def test_dead_player_pending(self) -> None:
        """DEAD 確定後の重複 PlayerDownedEvent もそのまま無視 (= 冪等)。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)
        timer = PlayerDeathGraceTimer()
        handler = _make_handler(reg=reg, timer=timer, tick=10)

        handler.handle(_make_downed_event(1))

        assert timer.is_pending(PlayerId(1)) is False

    def test_multiple_player_pending_independently(self) -> None:
        """複数 player の pending は独立に処理。"""
        reg = PlayerOutcomeRegistry.new_for_players(
            [PlayerId(1), PlayerId(2), PlayerId(3)]
        )
        timer = PlayerDeathGraceTimer()
        handler = _make_handler(reg=reg, timer=timer, tick=15)

        handler.handle(_make_downed_event(1))
        handler.handle(_make_downed_event(3))

        assert timer.is_pending(PlayerId(1)) is True
        assert timer.is_pending(PlayerId(2)) is False
        assert timer.is_pending(PlayerId(3)) is True


class TestTickProvider:
    """current_tick_provider が呼ばれて、その値が register の起点になる。"""

    def test_returns_provider_event_tick(self) -> None:
        """tick が時間とともに変わる前提 (= simulation 上は handle 時点の current tick)。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        ticks = iter([100, 200])

        def provider() -> int:
            return next(ticks)

        handler = PlayerDownedOutcomeHandler(
            outcome_registry=reg,
            grace_timer=timer,
            current_tick_provider=provider,
        )

        handler.handle(_make_downed_event(1))
        # 1 回目の provider 呼び出し結果 (= 100) が downed_at_tick
        overdue = timer.overdue_players(current_tick=130, grace_ticks=30)
        assert PlayerId(1) in overdue


class TestValidation:
    def test_outcome_registry_none_raises_type_error(self) -> None:
        """outcome registry None は TypeError。"""
        with pytest.raises(TypeError):
            PlayerDownedOutcomeHandler(
                outcome_registry=None,  # type: ignore[arg-type]
                grace_timer=PlayerDeathGraceTimer(),
                current_tick_provider=lambda: 0,
            )

    def test_grace_timer_none_raises_type_error(self) -> None:
        """grace timer None は TypeError。"""
        with pytest.raises(TypeError):
            PlayerDownedOutcomeHandler(
                outcome_registry=PlayerOutcomeRegistry(),
                grace_timer=None,  # type: ignore[arg-type]
                current_tick_provider=lambda: 0,
            )

    def test_current_tick_provider_none_raises_type_error(self) -> None:
        """current tick provider None は TypeError。"""
        with pytest.raises(TypeError):
            PlayerDownedOutcomeHandler(
                outcome_registry=PlayerOutcomeRegistry(),
                grace_timer=PlayerDeathGraceTimer(),
                current_tick_provider=None,  # type: ignore[arg-type]
            )
