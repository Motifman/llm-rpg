from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, EachPerson, NamedPerson, SubjectKind, Target
from ai_rpg_world.game_world.domain.effect.body_effects import DamageEffect, HealEffect
from ai_rpg_world.game_world.domain.effect.combined_effects import (
    ConditionalEffect,
    ForEveryoneEffect,
    ForSomeoneEffect,
    NoEffect,
    RandomBranchEffect,
    SequenceEffect,
)
from ai_rpg_world.game_world.domain.effect.item_effects import GiveItemEffect, TakeItemEffect
from ai_rpg_world.game_world.domain.effect.weight import Weight
from ai_rpg_world.game_world.domain.exception.effect_exception import NoBranchesException
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import NotEnoughItemsOfSpecException
from ai_rpg_world.game_world.domain.person import Down, StruckByPerson, WorldHappening
from ai_rpg_world.game_world.domain.value_object import Count, Damage, HealAmount, PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.effect._builders import (
    ALICE,
    BOB,
    CAROL,
    WORLD,
    EachPersonIsOneOf,
    FixedTruth,
    character,
    inventory,
    item_spec,
    vitals,
)
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_APPLE = item_spec("apple")
_ROPE = item_spec("rope")
_KNIFE = item_spec("knife")
_QUAKE = HappeningFired(HappeningForTests(HappeningId("quake")))
_ALICE_ACTS = ActionAttemptForTests(actor_id=ALICE)


def _world(fractions: tuple[float, ...] = ()) -> WorldInMemory:
    return WorldInMemory(
        world=WORLD,
        people=(ALICE, BOB, CAROL),
        vitals=(vitals(ALICE), vitals(BOB), vitals(CAROL)),
        inventories=(inventory(ALICE), inventory(BOB), inventory(CAROL)),
        fractions=fractions,
    )


def _hp(world: WorldInMemory, person: PersonId) -> int:
    return world.vitals[person].hp().current


def _requiring(*kinds: SubjectKind, uses_chance: bool = False) -> Requirements:
    return replace(Requirements.nothing(), subjects=frozenset(kinds), uses_chance=uses_chance)


def _some_of(*people: PersonId) -> PeopleSelection:
    return PeopleSelection(EachPersonIsOneOf(frozenset(people)))


class TestSequenceEffect:
    """SequenceEffect が、効果を並べた順に当て、集約が断ればそこで止めて例外をそのまま外へ出すことを保証する。"""

    def test_applies_steps_in_order(self) -> None:
        """りんごを与えてから、そのりんごを取ると、Alice の手元には何も残らない。"""
        world = _world()

        SequenceEffect((GiveItemEffect(Actor(), _APPLE, Count(1)), TakeItemEffect(Actor(), _APPLE, Count(1)))).apply(
            world.facts(), world.aggregates(), _ALICE_ACTS
        )

        assert world.inventories[ALICE].items() == ()

    def test_refusal_in_middle_comes_out_and_stops_later_steps(self) -> None:
        """りんごを与える → 持たない縄を取る → ナイフを与える、と並べると、縄で NotEnoughItemsOfSpecException が外へ出て、ナイフは与えない。"""
        world = _world()
        sequence = SequenceEffect(
            (
                GiveItemEffect(Actor(), _APPLE, Count(1)),
                TakeItemEffect(Actor(), _ROPE, Count(1)),
                GiveItemEffect(Actor(), _KNIFE, Count(1)),
            )
        )

        with pytest.raises(NotEnoughItemsOfSpecException):
            sequence.apply(world.facts(), world.aggregates(), _ALICE_ACTS)

        assert world.inventories[ALICE].count_of(_KNIFE.item_spec_id) == Count(0)

    def test_requires_what_every_step_requires(self) -> None:
        """要るものは、どの段の要るものも合わせたもの。"""
        sequence = SequenceEffect((HealEffect(Actor(), HealAmount(1)), HealEffect(Target(), HealAmount(1))))

        assert sequence.requirements() == _requiring(SubjectKind.ACTOR, SubjectKind.TARGET)


class TestConditionalEffect:
    """ConditionalEffect が、条件が真なら then を、偽なら otherwise を当てることを保証する。"""

    @pytest.mark.parametrize(("truth", "alice_hp", "bob_hp"), [(True, 7, 10), (False, 10, 7)])
    def test_applies_branch_by_condition(self, truth: bool, alice_hp: int, bob_hp: int) -> None:
        """条件が真なら Alice に、偽なら Bob に 3 の痛手を与える。"""
        world = _world()
        effect = ConditionalEffect(
            FixedTruth(truth),
            then=DamageEffect(NamedPerson(character(ALICE)), Damage(3)),
            otherwise=DamageEffect(NamedPerson(character(BOB)), Damage(3)),
        )

        effect.apply(world.facts(), world.aggregates(), _QUAKE)

        assert (_hp(world, ALICE), _hp(world, BOB)) == (alice_hp, bob_hp)

    def test_no_effect_otherwise_changes_nothing(self) -> None:
        """条件が偽で otherwise が NoEffect なら、誰も傷つかない。"""
        world = _world()

        ConditionalEffect(FixedTruth(False), DamageEffect(Actor(), Damage(3)), NoEffect()).apply(
            world.facts(), world.aggregates(), _ALICE_ACTS
        )

        assert _hp(world, ALICE) == 10

    def test_requires_condition_and_both_branches(self) -> None:
        """要るものは、条件と then と otherwise の要るものを合わせたもの。"""
        effect = ConditionalEffect(
            FixedTruth(True, _requiring(SubjectKind.CHOSEN_BY_GROUP)),
            then=HealEffect(Actor(), HealAmount(1)),
            otherwise=HealEffect(Target(), HealAmount(1)),
        )

        assert effect.requirements() == _requiring(SubjectKind.CHOSEN_BY_GROUP, SubjectKind.ACTOR, SubjectKind.TARGET)


class TestRandomBranchEffect:
    """RandomBranchEffect が、偶然を 1 つ引き、並べた枝の重みの割合で 1 つの枝を選んで当てることを保証する。"""

    @pytest.mark.parametrize(("fraction", "hurt"), [(0.0, ALICE), (0.24, ALICE), (0.25, BOB), (0.99, BOB)])
    def test_chooses_branch_by_weight_ratio(self, fraction: float, hurt: PersonId) -> None:
        """重み 1 で Alice、重み 3 で Bob を傷つける枝なら、引いた値が [0, 1/4) で Alice、[1/4, 1) で Bob が傷つく。"""
        world = _world(fractions=(fraction,))
        effect = RandomBranchEffect(
            (
                (Weight(1), DamageEffect(NamedPerson(character(ALICE)), Damage(3))),
                (Weight(3), DamageEffect(NamedPerson(character(BOB)), Damage(3))),
            )
        )

        effect.apply(world.facts(), world.aggregates(), _QUAKE)

        assert {person for person in (ALICE, BOB) if _hp(world, person) == 7} == {hurt}

    def test_requires_chance_and_every_branch(self) -> None:
        """要るものは、どの枝の要るものも合わせたものと、偶然。"""
        effect = RandomBranchEffect(
            ((Weight(1), HealEffect(Actor(), HealAmount(1))), (Weight(1), HealEffect(Target(), HealAmount(1))))
        )

        assert effect.requirements() == _requiring(SubjectKind.ACTOR, SubjectKind.TARGET, uses_chance=True)

    def test_without_branches_is_refused(self) -> None:
        """枝を 1 つも並べないと、作るときに NoBranchesException を投げる。"""
        with pytest.raises(NoBranchesException):
            RandomBranchEffect(())

    def test_weight_below_one_is_refused(self) -> None:
        """重みに 0 を渡すと、ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Weight(0)


class TestForEveryoneEffect:
    """ForEveryoneEffect が、選ばれた人ひとりずつに、その人を EachPerson として効果を当てることを保証する。"""

    def test_applies_to_each_selected_person(self) -> None:
        """Alice と Bob を選んで EachPerson に 3 の痛手を与えると、2 人が傷つき、Carol は傷つかない。"""
        world = _world()

        ForEveryoneEffect(_some_of(ALICE, BOB), DamageEffect(EachPerson(), Damage(3))).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        assert (_hp(world, ALICE), _hp(world, BOB), _hp(world, CAROL)) == (7, 7, 10)

    def test_outer_trigger_still_answers_fall_cause(self) -> None:
        """Bob の行為で Alice と Bob の全員に体力ぶんの痛手を与えると、Alice は Bob に、Bob は世界の出来事で倒れる。"""
        world = _world()

        ForEveryoneEffect(_some_of(ALICE, BOB), DamageEffect(EachPerson(), Damage(10))).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=BOB)
        )

        assert world.vitals[ALICE].life_state() == Down(fell_at=WorldTick(0), cause=StruckByPerson(BOB))
        assert world.vitals[BOB].life_state() == Down(fell_at=WorldTick(0), cause=WorldHappening())

    def test_requires_selection_and_effect_without_each_person(self) -> None:
        """要るものは、選び方 (Target を要る) と効果 (EachPerson と Actor を要る) を合わせ、中だけで使う EachPerson を外したもの。"""
        selection = PeopleSelection(FixedTruth(True, _requiring(SubjectKind.TARGET, SubjectKind.EACH_PERSON)))
        effect = ForEveryoneEffect(
            selection, SequenceEffect((HealEffect(EachPerson(), HealAmount(1)), HealEffect(Actor(), HealAmount(1))))
        )

        assert effect.requirements() == _requiring(SubjectKind.TARGET, SubjectKind.ACTOR)


class TestForSomeoneEffect:
    """ForSomeoneEffect が、選ばれた人から偶然で 1 人を選んで効果を当て、誰もいなければ何もしないことを保証する。"""

    @pytest.mark.parametrize(("fraction", "hurt"), [(0.0, ALICE), (0.5, BOB), (0.9, CAROL)])
    def test_applies_to_one_person_chosen_by_chance(self, fraction: float, hurt: PersonId) -> None:
        """Alice・Bob・Carol を選んだとき、引いた値で 3 等分した 1 人だけが傷つく。"""
        world = _world(fractions=(fraction,))

        ForSomeoneEffect(_some_of(ALICE, BOB, CAROL), DamageEffect(EachPerson(), Damage(3))).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        assert {person for person in (ALICE, BOB, CAROL) if _hp(world, person) == 7} == {hurt}

    def test_does_nothing_without_anyone_selected(self) -> None:
        """選ばれた人がいなければ、偶然を引かず、誰も傷つかない。"""
        world = _world(fractions=(0.5,))

        ForSomeoneEffect(_some_of(), DamageEffect(EachPerson(), Damage(3))).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        assert (_hp(world, ALICE), _hp(world, BOB), _hp(world, CAROL)) == (10, 10, 10)
        assert world.random.next_fraction() == 0.5

    def test_requires_chance_selection_and_effect_without_each_person(self) -> None:
        """要るものは、選び方 (Target を要る) と効果の要るものから EachPerson を外したものと、偶然。"""
        selection = PeopleSelection(FixedTruth(True, _requiring(SubjectKind.TARGET, SubjectKind.EACH_PERSON)))
        effect = ForSomeoneEffect(selection, HealEffect(EachPerson(), HealAmount(1)))

        assert effect.requirements() == _requiring(SubjectKind.TARGET, uses_chance=True)
