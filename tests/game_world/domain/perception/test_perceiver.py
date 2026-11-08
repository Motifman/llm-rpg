from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.perception_exception import DeadPersonCannotPerceiveAsLivingException
from ai_rpg_world.game_world.domain.perception import Aware, AwareOnWaking, LivingPerceiver, Unaware
from ai_rpg_world.game_world.domain.person.life_state import Dead
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.domain.perception._builders import ALICE, SQUARE, at, awake, departed, fallen


class TestLivingPerceiverNoticesSurroundings:
    """LivingPerceiver.notices_surroundings が、起きているか倒れているかと、自分が関わるかで気づき方を決めることを保証する。"""

    @pytest.mark.parametrize("involved", [True, False])
    def test_awake_person_is_aware_whether_involved_or_not(self, involved: bool) -> None:
        """起きている人は、自分が関わるかに関わらず周りに気づく (Aware)。"""
        assert awake(ALICE).notices_surroundings(involved) == Aware()

    def test_fallen_person_becomes_aware_on_waking_of_what_involves_them(self) -> None:
        """倒れている人は、自分が関わることには起きてから気づく (AwareOnWaking)。"""
        assert fallen(ALICE).notices_surroundings(True) == AwareOnWaking()

    def test_fallen_person_is_unaware_of_what_does_not_involve_them(self) -> None:
        """倒れている人は、自分が関わらないことには気づかない (Unaware)。"""
        assert fallen(ALICE).notices_surroundings(False) == Unaware()

    def test_dead_life_is_refused(self) -> None:
        """life に Dead を渡すと DeadPersonCannotPerceiveAsLivingException を投げる。死んだ人は去った人として知覚する。"""
        with pytest.raises(DeadPersonCannotPerceiveAsLivingException):
            LivingPerceiver(person=ALICE, life=Dead(died_at=WorldTick(3)), location=at(SQUARE), attentive=False)  # type: ignore[arg-type]


class TestDepartedPerceiverNoticesSurroundings:
    """DepartedPerceiver.notices_surroundings が、去った人はいつも周りに気づくことを保証する。"""

    @pytest.mark.parametrize("involved", [True, False])
    def test_departed_person_is_always_aware(self, involved: bool) -> None:
        """去った人は、自分が関わるかに関わらず周りに気づく (Aware)。"""
        assert departed(ALICE).notices_surroundings(involved) == Aware()
