from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, NamedPerson, SubjectKind, Target
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight
from ai_rpg_world.game_world.domain.effect.body_effects import (
    DamageEffect,
    HealEffect,
    RestEffect,
    ReviveEffect,
    SatisfyHungerEffect,
)
from ai_rpg_world.game_world.domain.person import Alive, Down, PersonVitals, StruckByPerson, WorldHappening
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    FatigueAmount,
    HealAmount,
    HitPoints,
    HungerAmount,
    Rate,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.effect._builders import ALICE, BOB, WORLD, character, vitals
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory


def _world(*people_vitals: PersonVitals, ticks: int = 0) -> WorldInMemory:
    world = WorldInMemory(world=WORLD, people=(ALICE, BOB), vitals=people_vitals)
    for _ in range(ticks):
        world.clock().advance(NoDayNight())
    return world


class TestDamageEffect:
    """DamageEffect が、傷ついた人の体力を減らし、倒れた理由をきっかけに尋ねることを保証する。"""

    def test_person_struck_by_another_falls_by_that_person(self) -> None:
        """Bob が Alice に体力ぶんの痛手を与えると、Alice は今の tick に倒れ、倒れた理由は StruckByPerson(Bob)。"""
        world = _world(vitals(ALICE, hp=10), ticks=3)
        bob_hits_alice = ActionAttemptForTests(actor_id=BOB, target=ALICE)

        DamageEffect(Target(), Damage(10)).apply(world.facts(), world.aggregates(), bob_hits_alice)

        assert world.vitals[ALICE].life_state() == Down(fell_at=WorldTick(3), cause=StruckByPerson(BOB))

    def test_person_hurt_by_own_action_falls_by_world_happening(self) -> None:
        """Alice が罠に触れて自分が傷つくと、倒れた理由は WorldHappening()。"""
        world = _world(vitals(ALICE, hp=4))
        alice_touches_trap = ActionAttemptForTests(actor_id=ALICE)

        DamageEffect(Actor(), Damage(4)).apply(world.facts(), world.aggregates(), alice_touches_trap)

        assert world.vitals[ALICE].life_state() == Down(fell_at=WorldTick(0), cause=WorldHappening())

    def test_person_hurt_by_happening_falls_by_world_happening(self) -> None:
        """出来事が名指しした Alice を傷つけると、倒れた理由は WorldHappening()。"""
        world = _world(vitals(ALICE, hp=4))
        rockfall = HappeningFired(HappeningForTests(HappeningId("rockfall")))

        DamageEffect(NamedPerson(character(ALICE)), Damage(4)).apply(world.facts(), world.aggregates(), rockfall)

        assert world.vitals[ALICE].life_state() == Down(fell_at=WorldTick(0), cause=WorldHappening())

    def test_damage_short_of_hit_points_only_lowers_them(self) -> None:
        """体力 10 の Alice に 3 の痛手を与えると、体力は 7 になり、起きたまま。"""
        world = _world(vitals(ALICE, hp=10))

        DamageEffect(Target(), Damage(3)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=BOB, target=ALICE)
        )

        assert world.vitals[ALICE].hp() == HitPoints(current=7, maximum=10)
        assert world.vitals[ALICE].life_state() == Alive()

    def test_requires_only_its_subject(self) -> None:
        """要るものは、傷つける人の主語 (Target) だけ。"""
        assert DamageEffect(Target(), Damage(1)).requirements() == Requirements(
            subjects=frozenset({SubjectKind.TARGET}),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
        )


class TestHealAndReviveEffect:
    """HealEffect と ReviveEffect が、その人の体力を戻すことを保証する。"""

    def test_heal_raises_hit_points(self) -> None:
        """体力 4 の Alice を 3 癒すと、体力は 7 になる。"""
        world = _world(vitals(ALICE, hp=4))

        HealEffect(Actor(), HealAmount(3)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
        )

        assert world.vitals[ALICE].hp() == HitPoints(current=7, maximum=10)

    def test_revive_wakes_fallen_person_with_rate_of_maximum(self) -> None:
        """倒れた Alice (最大体力 10) を率 0.5 で起こすと、体力 5 で起きている。"""
        world = _world(vitals(ALICE, hp=1))
        world.vitals[ALICE].take_damage(Damage(1), WorldTick(0), WorldHappening())

        ReviveEffect(Target(), Rate(0.5)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=BOB, target=ALICE)
        )

        assert world.vitals[ALICE].life_state() == Alive()
        assert world.vitals[ALICE].hp() == HitPoints(current=5, maximum=10)


class TestSatisfyHungerAndRestEffect:
    """SatisfyHungerEffect と RestEffect が、世界の規則で空腹と疲れを減らすことを保証する。"""

    def test_satisfy_hunger_lowers_hunger(self) -> None:
        """空腹 3 の Alice が 2 満たすと、空腹は 1 になる。"""
        world = _world(vitals(ALICE))
        rules = world.facts().rules()
        for tick in range(3):
            world.vitals[ALICE].pass_time(WorldTick(tick), rules.death, rules.hunger)

        SatisfyHungerEffect(Actor(), HungerAmount(2)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
        )

        assert world.vitals[ALICE].hunger() == HungerAmount(1)

    def test_rest_lowers_fatigue(self) -> None:
        """疲れ 4 の Alice が 3 休むと、疲れは 1 になる。"""
        world = _world(vitals(ALICE))
        rules = world.facts().rules()
        world.vitals[ALICE].exert(rules.fatigue)
        world.vitals[ALICE].exert(rules.fatigue)

        RestEffect(Actor(), FatigueAmount(3)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
        )

        assert world.vitals[ALICE].fatigue() == FatigueAmount(1)
