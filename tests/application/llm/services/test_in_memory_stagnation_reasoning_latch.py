"""InMemoryStagnationReasoningLatch の arm/consume の一発挙動と player 独立性を保証する。"""

import pytest

from ai_rpg_world.application.llm.services.in_memory_stagnation_reasoning_latch import (
    InMemoryStagnationReasoningLatch,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestInMemoryStagnationReasoningLatch:
    def test_arm_then_consume_returns_true_once(self) -> None:
        """arm した player を consume すると 1 度だけ True を返し、以降は False。"""
        latch = InMemoryStagnationReasoningLatch()
        latch.arm(PlayerId(1))
        assert latch.consume(PlayerId(1)) is True
        assert latch.consume(PlayerId(1)) is False

    def test_consume_without_arm_returns_false(self) -> None:
        """arm していない player の consume は False (熟考しない)。"""
        latch = InMemoryStagnationReasoningLatch()
        assert latch.consume(PlayerId(1)) is False

    def test_arm_is_idempotent(self) -> None:
        """同じ player を複数回 arm しても、consume で立つのは 1 回分 (次行動 1 回だけ)。"""
        latch = InMemoryStagnationReasoningLatch()
        latch.arm(PlayerId(1))
        latch.arm(PlayerId(1))
        assert latch.consume(PlayerId(1)) is True
        assert latch.consume(PlayerId(1)) is False

    def test_players_are_independent(self) -> None:
        """arm/consume は player ごとに独立している。"""
        latch = InMemoryStagnationReasoningLatch()
        latch.arm(PlayerId(1))
        assert latch.consume(PlayerId(2)) is False
        assert latch.consume(PlayerId(1)) is True

    def test_arm_rejects_non_player_id(self) -> None:
        """PlayerId 以外を渡すと TypeError。"""
        latch = InMemoryStagnationReasoningLatch()
        with pytest.raises(TypeError):
            latch.arm(1)  # type: ignore[arg-type]
