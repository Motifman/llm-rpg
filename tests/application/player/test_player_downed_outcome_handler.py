"""PlayerDownedOutcomeHandler の挙動検証 (Phase E-3)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.player.handlers.player_downed_outcome_handler import (
    PlayerDownedOutcomeHandler,
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


class TestHandler:
    def test_PlayerDownedEvent_受信で_outcome_が_DEAD_になる(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        handler = PlayerDownedOutcomeHandler(reg)

        handler.handle(_make_downed_event(1))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD

    def test_既に_RESCUED_なプレイヤーは_DEAD_に上書きされない(self) -> None:
        """救助直後の何らかのバグで HP=0 イベントが来ても、RESCUED を保持する。"""
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        reg.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        handler = PlayerDownedOutcomeHandler(reg)

        handler.handle(_make_downed_event(1))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED

    def test_複数プレイヤーの_DEAD_は_独立に処理(self) -> None:
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2), PlayerId(3)])
        handler = PlayerDownedOutcomeHandler(reg)

        handler.handle(_make_downed_event(1))
        handler.handle(_make_downed_event(3))

        assert reg.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD
        assert reg.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.UNRESOLVED
        assert reg.get_outcome(PlayerId(3)) is PlayerOutcomeEnum.DEAD
