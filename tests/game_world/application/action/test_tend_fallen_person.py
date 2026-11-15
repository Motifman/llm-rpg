from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.person_exception import PersonNotDownException
from ai_rpg_world.game_world.domain.exception.rules_exception import TendingNotDeclaredException
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending
from ai_rpg_world.game_world.domain.value_object import HitPoints
from tests.game_world.application.action.world_for_search_and_tend_tests import ALICE, BOB, WorldForSearchAndTend


class TestTendFallenPerson:
    """TendFallenPerson が、倒れた人を世界の介抱の規則のとおりに起こし、倒れていない人の介抱を断ることを保証する。"""

    def test_fallen_person_gets_up_with_revive_rate_of_hp(self) -> None:
        """倒れた bob を介抱すると ActionDone が返り、bob は起き上がって HP が最大 100 の半分 (介抱の率 0.5) になる。"""
        world = WorldForSearchAndTend()
        world.knock_down(BOB)

        reply = world.tend(ALICE, BOB)

        assert reply == ActionDone()
        session = world.read()
        vitals = session.facts().vitals(BOB)
        assert vitals.can_act() is True
        assert vitals.hp() == HitPoints(50, 100)
        session.roll_back()

    def test_person_not_down_is_refused(self) -> None:
        """倒れていない bob を介抱しようとすると PERSON_NOT_DOWN の RefusalCode で断られ、HP は変わらない。"""
        world = WorldForSearchAndTend()

        reply = world.tend(ALICE, BOB)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(PersonNotDownException.error_code))
        session = world.read()
        assert session.facts().vitals(BOB).hp() == HitPoints(100, 100)
        session.roll_back()

    def test_world_without_tending_raises_instead_of_refusing(self) -> None:
        """介抱の規則が無い世界 (NoTending) で介抱が届くと、断りの返事ではなく TendingNotDeclaredException を投げる。"""
        world = WorldForSearchAndTend(tending=NoTending())
        world.knock_down(BOB)

        with pytest.raises(TendingNotDeclaredException):
            world.tend(ALICE, BOB)
