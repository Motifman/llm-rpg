from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.acquaintance import (
    Acquaintance,
    AcquaintanceInvalid,
)


class TestAcquaintance:
    """Acquaintance が、相手と会った回数と時期を Being のターン数で持つことを保証する。"""

    def test_first_meeting_counts_one_and_fixes_both_turns(self) -> None:
        """初めて会った記録は、会った回数が 1 で、初めて会ったターンと最後に会ったターンが同じになる。"""
        met = Acquaintance.first_meeting(environment_name="島", name="ノア", turn=3)

        assert (met.met_count, met.first_met_turn, met.last_met_turn) == (1, 3, 3)
        assert met.is_first_meeting

    def test_meeting_again_advances_only_the_last_turn(self) -> None:
        """もう一度会うと回数が増え、最後に会ったターンだけが進み、初めて会ったターンは変わらない。"""
        met = Acquaintance.first_meeting(environment_name="島", name="ノア", turn=3)

        again = met.met_again(turn=7)

        assert (again.met_count, again.first_met_turn, again.last_met_turn) == (2, 3, 7)
        assert not again.is_first_meeting

    def test_meeting_again_in_an_earlier_turn_is_rejected(self) -> None:
        """最後に会ったターンより前のターンで会い直そうとすると AcquaintanceInvalid を投げる。"""
        met = Acquaintance.first_meeting(environment_name="島", name="ノア", turn=7)

        with pytest.raises(AcquaintanceInvalid):
            met.met_again(turn=6)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"environment_name": " ", "name": "ノア", "turn": 0},
            {"environment_name": "島", "name": "", "turn": 0},
            {"environment_name": "島", "name": "ノア", "turn": -1},
            {"environment_name": "島", "name": "ノア", "turn": True},
        ],
    )
    def test_blank_names_or_invalid_turn_are_rejected(self, kwargs: dict) -> None:
        """環境の名前や相手の名前が空、またはターンが負か整数でないとき AcquaintanceInvalid を投げる。"""
        with pytest.raises(AcquaintanceInvalid):
            Acquaintance.first_meeting(**kwargs)

    def test_inconsistent_counts_are_rejected(self) -> None:
        """会った回数が 1 未満、または最後に会ったターンが初めて会ったターンより前なら作れない。"""
        with pytest.raises(AcquaintanceInvalid):
            Acquaintance(
                environment_name="島", name="ノア",
                first_met_turn=2, last_met_turn=2, met_count=0,
            )
        with pytest.raises(AcquaintanceInvalid):
            Acquaintance(
                environment_name="島", name="ノア",
                first_met_turn=5, last_met_turn=4, met_count=2,
            )
