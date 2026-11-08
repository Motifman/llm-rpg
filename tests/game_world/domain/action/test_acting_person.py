from __future__ import annotations

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.person import StruckByPerson, WorldHappening
from ai_rpg_world.game_world.domain.value_object import PersonId

_ALICE = PersonId("alice")
_BOB = PersonId("bob")


class TestFallCauseFrom:
    """fall_cause_from が、行う人と傷ついた人から倒れた理由を決めることを保証する。"""

    def test_someone_else_hurt_by_the_acting_person_was_struck(self) -> None:
        """alice の行為で bob が傷ついたとき、倒れた理由は StruckByPerson(alice)。"""
        assert fall_cause_from(_ALICE, victim=_BOB) == StruckByPerson(_ALICE)

    def test_acting_person_hurting_themself_is_a_world_happening(self) -> None:
        """alice の行為で alice 自身が傷ついたとき (罠に触れたなど)、倒れた理由は WorldHappening。"""
        assert fall_cause_from(_ALICE, victim=_ALICE) == WorldHappening()

    def test_no_acting_person_is_a_world_happening(self) -> None:
        """行う人がいないとき、bob が傷ついた倒れた理由は WorldHappening。"""
        assert fall_cause_from(NoActingPerson(), victim=_BOB) == WorldHappening()
