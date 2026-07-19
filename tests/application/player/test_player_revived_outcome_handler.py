"""PlayerRevivedOutcomeHandler の挙動検証 (Issue #621)。

PlayerRevivedEvent を受けて PlayerDeathGraceTimer から pending を消す。
これにより 30 tick 経過判定の対象から外れ、DEAD 確定が回避される。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.player.handlers.player_revived_outcome_handler import (
    PlayerRevivedOutcomeHandler,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_revived_event(player_id: int, hp: int = 40) -> PlayerRevivedEvent:
    return PlayerRevivedEvent.create(
        aggregate_id=PlayerId(player_id),
        aggregate_type="PlayerStatusAggregate",
        hp_recovered=hp,
        total_hp=hp,
    )


class TestPendingCancellation:
    def test_player_revived_event_grace_timer_cancel(self) -> None:
        """PlayerRevivedEvent 受信で grace timer から cancel される。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        handler = PlayerRevivedOutcomeHandler(grace_timer=timer)

        handler.handle(_make_revived_event(1))

        assert timer.is_pending(PlayerId(1)) is False

    def test_pending_player_revived_event_raises_exception(self) -> None:
        """revive event が pending でない player に飛んできても破綻しない冪等性。

        例: scenario_event で「ダウンせず復活」のような変則ケースを将来許容
        するためのガード。現状では発生しないが防御的にテストで保証する。
        """
        timer = PlayerDeathGraceTimer()
        handler = PlayerRevivedOutcomeHandler(grace_timer=timer)

        handler.handle(_make_revived_event(99))  # 例外なく完了

    def test_other_player_pending_does_not_affect(self) -> None:
        """他 player の pending には 影響しない。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        timer.register(PlayerId(2), downed_at_tick=15)
        handler = PlayerRevivedOutcomeHandler(grace_timer=timer)

        handler.handle(_make_revived_event(1))

        assert timer.is_pending(PlayerId(1)) is False
        assert timer.is_pending(PlayerId(2)) is True


class TestValidation:
    def test_grace_timer_none_raises_type_error(self) -> None:
        """grace timer None は TypeError。"""
        with pytest.raises(TypeError):
            PlayerRevivedOutcomeHandler(grace_timer=None)  # type: ignore[arg-type]
