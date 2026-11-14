from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import NamedPerson, SubjectKind
from ai_rpg_world.game_world.domain.effect.whereabouts_effects import (
    PutIntoSectionEffect,
    RemoveBodyEffect,
    TakeOutOfSectionEffect,
    TeleportEffect,
)
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    OccupantNotPlacedException,
    SectionFullException,
)
from ai_rpg_world.game_world.domain.person import PersonVitals, WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, DepartedPerson, OpenArea, PersonBody
from tests.game_world.domain.effect._builders import ALICE, BOB, WORLD, character, vitals
from tests.game_world.domain.whereabouts._builders import section, spot
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import world_in_memory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_PLAZA = spot("plaza")
_WELL = spot("well")
_BENCH = section("bench", "plaza", capacity=1)
_QUAKE = HappeningFired(HappeningForTests(HappeningId("quake")))


def _fallen(person: PersonId) -> PersonVitals:
    fallen = vitals(person, hp=1)
    fallen.take_damage(Damage(1), WorldTick(0), WorldHappening())
    return fallen


def _dead(person: PersonId) -> PersonVitals:
    dead = _fallen(person)
    dead.pass_time(WorldTick(100), world_rules_for_tests().death, world_rules_for_tests().hunger)
    return dead


def _world(*people_vitals: PersonVitals, departed_persons_act: bool = False) -> WorldSession:
    world = world_in_memory(
        world=WORLD,
        rules=replace(world_rules_for_tests(), departed_persons_act=departed_persons_act),
        people=tuple(v.person for v in people_vitals),
        spots=(_PLAZA, _WELL),
        vitals=people_vitals,
    )
    for person_vitals in people_vitals:
        world.aggregates().whereabouts().place(PersonBody(person_vitals.person), _PLAZA)
    return world


def _named(person: PersonId) -> NamedPerson:
    return NamedPerson(character(person))


def _depart(world: WorldSession, person: PersonId) -> None:
    world.aggregates().whereabouts().place(DepartedPerson(person), _PLAZA)


class TestTeleportEffect:
    """TeleportEffect が、去った人として動いていれば去った人を、それ以外は体を、宣言の場所へ移すことを保証する。"""

    def test_moves_living_person_body(self) -> None:
        """広場にいる Alice を井戸へ移すと、Alice の体は井戸にいる。"""
        world = _world(vitals(ALICE))

        TeleportEffect(_named(ALICE), _WELL).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().whereabouts().is_at(PersonBody(ALICE), _WELL)

    def test_moves_departed_person_and_leaves_body(self) -> None:
        """去った人が動く世界で、死んだ Alice を井戸へ移すと、去った Alice が井戸にいて、体は広場に残る。"""
        world = _world(_dead(ALICE), departed_persons_act=True)
        _depart(world, ALICE)

        TeleportEffect(_named(ALICE), _WELL).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().whereabouts().is_at(DepartedPerson(ALICE), _WELL)
        assert world.aggregates().whereabouts().is_at(PersonBody(ALICE), _PLAZA)

    def test_moves_dead_body_when_departed_persons_do_not_act(self) -> None:
        """去った人が動かない世界で、死んだ Alice を井戸へ移すと、体が井戸へ移る。"""
        world = _world(_dead(ALICE), departed_persons_act=False)

        TeleportEffect(_named(ALICE), _WELL).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().whereabouts().is_at(PersonBody(ALICE), _WELL)

    def test_requires_only_its_subject(self) -> None:
        """要るものは、移す人の主語だけ。"""
        assert TeleportEffect(_named(ALICE), _WELL).requirements() == Requirements(
            subjects=frozenset({SubjectKind.NAMED_PERSON}),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )


class TestPutIntoAndTakeOutOfSectionEffect:
    """区画に入れる・出す効果が、定員に倒れた人と死んだ人を数えずに区画へ出し入れすることを保証する。"""

    def test_puts_person_into_section(self) -> None:
        """Alice を長椅子に入れると、Alice の体は長椅子の中にいる。"""
        world = _world(vitals(ALICE))

        PutIntoSectionEffect(_named(ALICE), _BENCH).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().whereabouts().is_in_section(PersonBody(ALICE), _BENCH)

    @pytest.mark.parametrize("make_bob", [_fallen, _dead])
    def test_fallen_or_dead_bodies_do_not_fill_section(self, make_bob: Callable[[PersonId], PersonVitals]) -> None:
        """定員 1 の長椅子に倒れた (または死んだ) Bob の体があっても、Alice を入れられる。"""
        world = _world(vitals(ALICE), make_bob(BOB))
        world.aggregates().whereabouts().enter_section(PersonBody(BOB), _BENCH, frozenset({BOB}))

        PutIntoSectionEffect(_named(ALICE), _BENCH).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().whereabouts().is_in_section(PersonBody(ALICE), _BENCH)

    def test_living_person_fills_section(self) -> None:
        """定員 1 の長椅子に起きている Bob がいると、Whereabouts が SectionFullException で断る。"""
        world = _world(vitals(ALICE), vitals(BOB))
        world.aggregates().whereabouts().enter_section(PersonBody(BOB), _BENCH, frozenset())

        with pytest.raises(SectionFullException):
            PutIntoSectionEffect(_named(ALICE), _BENCH).apply(world.facts(), world.aggregates(), _QUAKE)

    def test_takes_person_out_of_section(self) -> None:
        """長椅子にいる Alice を出すと、Alice は広場の区画の外にいる。"""
        world = _world(vitals(ALICE))
        world.aggregates().whereabouts().enter_section(PersonBody(ALICE), _BENCH, frozenset())

        TakeOutOfSectionEffect(_named(ALICE)).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().whereabouts().location_of(PersonBody(ALICE)) == AtSpot(
            spot=_PLAZA.spot_id, section=OpenArea()
        )


class TestRemoveBodyEffect:
    """RemoveBodyEffect が、その人の体だけを世界から除くことを保証する。"""

    def test_removes_body_and_keeps_departed_person(self) -> None:
        """去った人が動く世界で死んだ Alice の体を除くと、体は居場所を失い、去った Alice は広場に残る。"""
        world = _world(_dead(ALICE), departed_persons_act=True)
        _depart(world, ALICE)

        RemoveBodyEffect(_named(ALICE)).apply(world.facts(), world.aggregates(), _QUAKE)

        with pytest.raises(OccupantNotPlacedException):
            world.aggregates().whereabouts().location_of(PersonBody(ALICE))
        assert world.aggregates().whereabouts().is_at(DepartedPerson(ALICE), _PLAZA)
