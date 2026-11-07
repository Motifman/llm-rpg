from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.exception.person_exception import (
    OutcomeAlreadyDecidedException,
    PersonListedTwiceException,
    PersonNotInWorldException,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import (
    DeclaredOutcome,
    Died,
    PersonOutcomeDecidedEvent,
    PersonOutcomes,
    Undecided,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, OutcomeId, PersonId, WorldId

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")
_ESCAPED = DeclaredOutcome(
    OutcomeDeclaration(
        outcome_id=OutcomeId("escaped"),
        name=DisplayName("脱出"),
        announcement=TextWithUnassignedPeople("{actor}は島を出た。"),
    )
)


def _outcomes() -> PersonOutcomes:
    return PersonOutcomes.start(_WORLD, (_ALICE, _BOB, _CAROL))


class TestStart:
    """PersonOutcomes.start が、世界の人全員の結末を未決で始めることを保証する。"""

    def test_everyone_starts_undecided(self) -> None:
        """始めは全員の結末が Undecided で、all_decided は偽、undecided_people は渡した順の全員。"""
        outcomes = _outcomes()

        assert outcomes.outcome_of(_ALICE) == Undecided()
        assert not outcomes.all_decided()
        assert outcomes.undecided_people() == (_ALICE, _BOB, _CAROL)
        assert outcomes.get_events() == []

    def test_keeps_the_world_as_its_id(self) -> None:
        """世界に 1 つの集約として、WorldId を持つ。"""
        assert _outcomes().world == _WORLD

    def test_listing_a_person_twice_raises_domain_exception(self) -> None:
        """同じ人を 2 回渡すと PersonListedTwiceException を投げる。"""
        with pytest.raises(PersonListedTwiceException):
            PersonOutcomes.start(_WORLD, (_ALICE, _ALICE))


class TestDecide:
    """decide が人ごとに結末を一度だけ決めることを保証する。"""

    def test_deciding_records_the_outcome_and_raises_event(self) -> None:
        """宣言した結末を決めると outcome_of がそれを返し、PersonOutcomeDecidedEvent をためる。"""
        outcomes = _outcomes()

        outcomes.decide(_BOB, _ESCAPED)

        assert outcomes.outcome_of(_BOB) == _ESCAPED
        assert outcomes.undecided_people() == (_ALICE, _CAROL)
        [event] = outcomes.get_events()
        assert isinstance(event, PersonOutcomeDecidedEvent)
        assert (event.world, event.person, event.outcome) == (_WORLD, _BOB, _ESCAPED)

    def test_death_is_a_built_in_outcome(self) -> None:
        """宣言しなくても、死 (Died) を結末として決められる。"""
        outcomes = _outcomes()

        outcomes.decide(_ALICE, Died())

        assert outcomes.outcome_of(_ALICE) == Died()

    def test_deciding_twice_raises_domain_exception_and_keeps_the_first(self) -> None:
        """一度決まった結末をもう一度決めると OutcomeAlreadyDecidedException を投げ、最初の結末のままでイベントもためない。"""
        outcomes = _outcomes()
        outcomes.decide(_ALICE, Died())
        outcomes.clear_events()

        with pytest.raises(OutcomeAlreadyDecidedException):
            outcomes.decide(_ALICE, _ESCAPED)

        assert outcomes.outcome_of(_ALICE) == Died()
        assert outcomes.get_events() == []

    def test_all_decided_once_everyone_has_an_outcome(self) -> None:
        """全員の結末が決まると all_decided が真になり、undecided_people は空。"""
        outcomes = _outcomes()

        for person in (_ALICE, _BOB, _CAROL):
            outcomes.decide(person, Died())

        assert outcomes.all_decided()
        assert outcomes.undecided_people() == ()

    def test_deciding_for_a_person_not_in_the_world_raises_domain_exception(self) -> None:
        """世界にいない人の結末を決めると PersonNotInWorldException を投げる。"""
        with pytest.raises(PersonNotInWorldException):
            _outcomes().decide(PersonId("dave"), Died())

    def test_asking_about_a_person_not_in_the_world_raises_domain_exception(self) -> None:
        """世界にいない人の結末を聞くと PersonNotInWorldException を投げる。"""
        with pytest.raises(PersonNotInWorldException):
            _outcomes().outcome_of(PersonId("dave"))
