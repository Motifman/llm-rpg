from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnInvalid,
    MemoryTurnReader,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

RIO = BeingId("being-rio")
NOA = BeingId("being-noa")


class TestAdvancingTheTurn:
    """記憶のターン数が Being ごとに 0 から 1 手ずつ進む挙動を保証する。"""

    def test_turn_starts_at_zero(self) -> None:
        """一度も手を受け取っていない Being のターン数は 0。"""
        clock = InMemoryMemoryTurnClock()

        assert clock.current_turn(RIO) == 0

    def test_each_advance_moves_turn_by_one(self) -> None:
        """1 手を受け取るたびにターン数が 1 進み、進めたあとの値を返す。"""
        clock = InMemoryMemoryTurnClock()

        advanced = [clock.advance_turn(RIO) for _ in range(3)]

        assert advanced == [1, 2, 3]
        assert clock.current_turn(RIO) == 3

    def test_turn_is_counted_per_being(self) -> None:
        """ある Being の手は、別の Being のターン数を進めない。"""
        clock = InMemoryMemoryTurnClock()

        clock.advance_turn(RIO)

        assert clock.current_turn(NOA) == 0

    def test_turn_can_be_read_through_memory_turn_reader(self) -> None:
        """時計は MemoryTurnReader として渡せ、その口から進めたあとのターン数が読める。"""
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(RIO)
        clock.advance_turn(RIO)

        reader: MemoryTurnReader = clock

        assert isinstance(reader, MemoryTurnReader)
        assert reader.current_turn(RIO) == 2


class TestReplacingTheTurn:
    """snapshot の復元で、Being のターン数を置き換える挙動を保証する。"""

    def test_replace_overwrites_the_advanced_turn(self) -> None:
        """置き換えると、それまで進めたターン数は残らず、置き換えた値から進む。"""
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(RIO)

        clock.replace_all_by_being(RIO, turn=17)

        assert clock.current_turn(RIO) == 17
        assert clock.advance_turn(RIO) == 18

    def test_replace_with_zero_resets_the_turn(self) -> None:
        """0 で置き換えると、まだ手を受け取っていない Being と同じく 0 を返す。"""
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(RIO)

        clock.replace_all_by_being(RIO, turn=0)

        assert clock.current_turn(RIO) == 0

    def test_replace_does_not_touch_other_beings(self) -> None:
        """ある Being のターン数を置き換えても、別の Being のターン数は変わらない。"""
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(NOA)

        clock.replace_all_by_being(RIO, turn=5)

        assert clock.current_turn(NOA) == 1

    @pytest.mark.parametrize("turn", [-1, True, 1.5, "3"], ids=["negative", "bool", "float", "str"])
    def test_replace_with_invalid_turn_raises_and_keeps_the_turn(self, turn: object) -> None:
        """0 以上の int でない値で置き換えようとすると MemoryTurnInvalid を投げ、それまでのターン数を残す。"""
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(RIO)

        with pytest.raises(MemoryTurnInvalid, match="turn"):
            clock.replace_all_by_being(RIO, turn=turn)  # type: ignore[arg-type]

        assert clock.current_turn(RIO) == 1
