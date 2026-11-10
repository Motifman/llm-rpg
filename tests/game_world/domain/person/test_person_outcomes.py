from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.person_exception import (
    OutcomeAlreadyDecidedException,
    PersonListedTwiceException,
    PersonNotInWorldException,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import (
    DeclaredOutcome,
    Died,
    OutcomeOfPerson,
    PersonOutcomeDecidedEvent,
    PersonOutcomes,
    PersonOutcomesMemento,
    Undecided,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, OutcomeId, PersonId, WorldId
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

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


_DESIGN = compose_world(
    nouns(
        spots=(spot("beach"),),
        characters=(character("alice", "beach"), character("bob", "beach"), character("carol", "beach")),
        outcomes=(_ESCAPED.outcome,),
    )
)


class TestPersonOutcomesMemento:
    """PersonOutcomes を memento から作り直すと、決まった結末と未決の人とその順が元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_outcomes_answer_like_the_original(self) -> None:
        """alice が死に、bob が脱出したあと作り直すと、memento も各人の結末も元と同じで、未決は carol だけ。"""
        outcomes = _outcomes()
        outcomes.decide(_ALICE, Died())
        outcomes.decide(_BOB, _ESCAPED)

        rebuilt = rebuilt_from_memento(outcomes, _DESIGN)

        assert rebuilt.memento() == outcomes.memento()
        assert rebuilt.memento() != _outcomes().memento()
        assert rebuilt.world == _WORLD
        assert rebuilt.outcome_of(_ALICE) == Died()
        assert rebuilt.outcome_of(_BOB) == _ESCAPED
        assert rebuilt.undecided_people() == (_CAROL,)

    def test_rebuilt_outcomes_keep_the_order_of_people(self) -> None:
        """carol・alice・bob の順で始めた結末を作り直すと、undecided_people もその順で返る。"""
        outcomes = PersonOutcomes.start(_WORLD, (_CAROL, _ALICE, _BOB))

        assert rebuilt_from_memento(outcomes, _DESIGN).undecided_people() == (_CAROL, _ALICE, _BOB)

    def test_rebuilt_outcomes_still_refuse_deciding_twice(self) -> None:
        """alice が死んだあと作り直してから alice の結末を決めると、OutcomeAlreadyDecidedException を投げる。"""
        outcomes = _outcomes()
        outcomes.decide(_ALICE, Died())
        rebuilt = rebuilt_from_memento(outcomes, _DESIGN)

        with pytest.raises(OutcomeAlreadyDecidedException):
            rebuilt.decide(_ALICE, _ESCAPED)

    def test_rebuilding_records_no_event(self) -> None:
        """結末を決めたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        outcomes = _outcomes()
        outcomes.decide(_ALICE, Died())

        assert rebuilt_from_memento(outcomes, _DESIGN).get_events() == []


class TestPersonOutcomesMementoRefusals:
    """PersonOutcomes の memento が、宣言に無い結末や人、同じ人の重なりを持つとき、作り直しを断ることを保証する。"""

    def test_outcome_not_declared_is_refused(self) -> None:
        """alice の結末が宣言に無い drowned の memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = PersonOutcomesMemento(
            world_id=_WORLD,
            outcomes=(
                OutcomeOfPerson(_ALICE, OutcomeId("drowned")),
                OutcomeOfPerson(_BOB, Undecided()),
                OutcomeOfPerson(_CAROL, Undecided()),
            ),
        )

        with pytest.raises(UndeclaredNounException):
            PersonOutcomes.from_memento(memento, _DESIGN)

    def test_person_not_declared_is_refused(self) -> None:
        """宣言に無い dave を未決で持つ memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = PersonOutcomesMemento(world_id=_WORLD, outcomes=(OutcomeOfPerson(PersonId("dave"), Undecided()),))

        with pytest.raises(UndeclaredNounException):
            PersonOutcomes.from_memento(memento, _DESIGN)

    def test_declared_person_missing_is_refused(self) -> None:
        """宣言にいる carol の行が無く、alice と bob だけが未決の memento から作り直すと、MementoDoesNotMatchDesignException を投げる。"""
        memento = PersonOutcomesMemento(
            world_id=_WORLD, outcomes=(OutcomeOfPerson(_ALICE, Undecided()), OutcomeOfPerson(_BOB, Undecided()))
        )

        with pytest.raises(MementoDoesNotMatchDesignException):
            PersonOutcomes.from_memento(memento, _DESIGN)

    def test_same_person_twice_is_refused(self) -> None:
        """alice が死んだと未決の 2 つある memento を作ると、RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            PersonOutcomesMemento(
                world_id=_WORLD, outcomes=(OutcomeOfPerson(_ALICE, Died()), OutcomeOfPerson(_ALICE, Undecided()))
            )
