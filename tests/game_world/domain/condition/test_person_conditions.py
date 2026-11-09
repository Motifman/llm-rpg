from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.membership_condition import IsMemberCondition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import (
    AllOutcomesDecidedCondition,
    FatigueAtLeastCondition,
    GoldAtLeastCondition,
    HasItemCondition,
    HungerAtLeastCondition,
    IsAliveCondition,
    IsAtSpotCondition,
    IsDownCondition,
    IsHoldingCondition,
    IsInSectionCondition,
    OutcomeIsCondition,
    PeopleCountAtLeastCondition,
    SearchCountAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.subject import Actor, EachPerson, SubjectKind, Target
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import MembershipVisibility
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    LastsIndefinitely,
    NotALightSource,
)
from ai_rpg_world.game_world.domain.objects_and_items import Item, PersonInventory
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import Died, StruckByPerson
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import (
    HungerLevel,
    HungerLevelName,
    HungerRule,
    NoStarvationDamage,
)
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Count,
    Damage,
    DescriptionText,
    DisplayName,
    FatigueAmount,
    Gold,
    HandsNeeded,
    HungerAmount,
    ItemSpecId,
    Ticks,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody, Route
from tests.game_world.domain.condition._builders import ALICE, BOB, CAROL, WORLD, group, vitals
from tests.game_world.domain.whereabouts._builders import path, section, spot
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_in_memory import WorldInMemory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)
_ALICE_TO_BOB = ActionAttemptForTests(actor_id=ALICE, target=BOB)
_SQUARE = spot("square")
_WELL_SIDE = spot("well_side")
_LANE = path("lane", "square", "well_side", ticks=2)
_BENCH = section("bench", "square")
_APPLE = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("apple"),
    name=DisplayName("りんご"),
    description=DescriptionText("赤いりんご"),
    state_keys=(),
    lights_up=NotALightSource(),
    hands_needed=HandsNeeded(1),
    lasts=LastsIndefinitely(),
)
_PEAR = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("pear"),
    name=DisplayName("梨"),
    description=DescriptionText("黄色い梨"),
    state_keys=(),
    lights_up=NotALightSource(),
    hands_needed=HandsNeeded(1),
    lasts=LastsIndefinitely(),
)
_HUNGER = HungerRule(
    per_tick=HungerAmount(1),
    limit=HungerAmount(10),
    starvation_damage=NoStarvationDamage(),
    levels=(HungerLevel(starts_at=HungerAmount(0), name=HungerLevelName("満腹")),),
)
_FATIGUE = FatigueRule(
    per_exertion=FatigueAmount(3),
    limit=FatigueAmount(10),
    levels=(FatigueLevel(starts_at=FatigueAmount(0), name=FatigueLevelName("元気")),),
)


def _world(*, departed_persons_act: bool = False) -> WorldInMemory:
    people = (ALICE, BOB, CAROL)
    return WorldInMemory(
        world=WORLD,
        rules=replace(world_rules_for_tests(), departed_persons_act=departed_persons_act),
        people=people,
        spots=(_SQUARE, _WELL_SIDE),
        passages=(_LANE,),
        vitals=tuple(vitals(person) for person in people),
        inventories=tuple(PersonInventory(person, Capacity(5)) for person in people),
    )


def _carry(a_world: WorldInMemory, spec: ItemSpecDeclaration, item_id: str, *, hold: bool = False) -> None:
    item = Item.come_into_world(ItemInstanceId(item_id), spec, WorldTick(0))
    a_world.items[item.item_id] = item
    a_world.inventories[ALICE].receive(item.item_id, item.spec_id)
    if hold:
        a_world.inventories[ALICE].hold(item.item_id, HandsNeeded(1))


def _kill_alice(a_world: WorldInMemory) -> None:
    a_world.vitals[ALICE].take_damage(Damage(5), WorldTick(0), StruckByPerson(BOB))
    a_world.vitals[ALICE].pass_time(WorldTick(0), DeathRule(grace=Ticks(0)), _HUNGER)


class TestCarriedThings:
    """HasItemCondition・IsHoldingCondition・GoldAtLeastCondition が facts.inventory() と facts.item() を読むことを保証する。"""

    def test_has_item_counts_by_spec(self) -> None:
        """りんご 2 つと梨 1 つを持つ alice は、りんごを 2 つ以上持つ条件で真、3 つ以上で偽。"""
        a_world = _world()
        for item_id in ("apple-1", "apple-2"):
            _carry(a_world, _APPLE, item_id)
        _carry(a_world, _PEAR, "pear-1")

        assert HasItemCondition(who=Actor(), item_spec=_APPLE, count=Count(2), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )
        assert not HasItemCondition(who=Actor(), item_spec=_APPLE, count=Count(3), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_is_holding_looks_at_hands_only(self) -> None:
        """梨を手に持ち、りんごを荷にしまった alice は、梨を手に持つ条件で真、りんごを手に持つ条件で偽。"""
        a_world = _world()
        _carry(a_world, _PEAR, "pear-1", hold=True)
        _carry(a_world, _APPLE, "apple-1")

        assert IsHoldingCondition(who=Actor(), item_spec=_PEAR, failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)
        assert not IsHoldingCondition(who=Actor(), item_spec=_APPLE, failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_gold_at_least(self) -> None:
        """7 ゴールドを持つ alice は、7 以上で真、8 以上で偽。"""
        a_world = _world()
        a_world.inventories[ALICE].earn(Gold(7))

        assert GoldAtLeastCondition(who=Actor(), amount=Gold(7), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )
        assert not GoldAtLeastCondition(who=Actor(), amount=Gold(8), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_subject_is_resolved_from_the_trigger(self) -> None:
        """相手 (bob) について問う条件は、行う人 alice ではなく bob の持ち物を見て、TARGET を要る。"""
        a_world = _world()
        a_world.inventories[BOB].earn(Gold(3))
        condition = GoldAtLeastCondition(who=Target(), amount=Gold(3), failure_text=NoText())

        assert condition.holds(a_world.facts(), _ALICE_TO_BOB)
        assert condition.requirements().subjects == frozenset({SubjectKind.TARGET})


class TestWhereaboutsOfPeople:
    """IsAtSpotCondition と IsInSectionCondition が、生きた体か去った人の居場所を見ることを保証する。"""

    def test_is_at_spot_looks_at_the_body(self) -> None:
        """広場にいる alice は、広場にいる条件で真、井戸端にいる条件で偽。"""
        a_world = _world()
        a_world.whereabouts.place(PersonBody(ALICE), _SQUARE)

        assert IsAtSpotCondition(who=Actor(), spot=_SQUARE, failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)
        assert not IsAtSpotCondition(who=Actor(), spot=_WELL_SIDE, failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_departed_person_is_looked_at_when_departed_persons_act(self) -> None:
        """死んだ alice の体が広場、去った人が井戸端にいて、去った人が動く世界なら、井戸端にいる条件が真で広場は偽。"""
        a_world = _world(departed_persons_act=True)
        a_world.whereabouts.place(PersonBody(ALICE), _SQUARE)
        a_world.whereabouts.place(DepartedPerson(ALICE), _WELL_SIDE)
        _kill_alice(a_world)

        assert IsAtSpotCondition(who=Actor(), spot=_WELL_SIDE, failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)
        assert not IsAtSpotCondition(who=Actor(), spot=_SQUARE, failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)

    def test_body_is_looked_at_when_departed_persons_do_not_act(self) -> None:
        """同じ置き方でも、去った人が動かない世界なら、死んだ alice の体のある広場にいる条件が真。"""
        a_world = _world(departed_persons_act=False)
        a_world.whereabouts.place(PersonBody(ALICE), _SQUARE)
        a_world.whereabouts.place(DepartedPerson(ALICE), _WELL_SIDE)
        _kill_alice(a_world)

        assert IsAtSpotCondition(who=Actor(), spot=_SQUARE, failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)

    def test_is_in_section(self) -> None:
        """広場のベンチに入った alice はベンチにいる条件で真、入る前は偽。"""
        a_world = _world()
        a_world.whereabouts.place(PersonBody(ALICE), _SQUARE)
        condition = IsInSectionCondition(who=Actor(), section=_BENCH, failure_text=NoText())
        assert not condition.holds(a_world.facts(), _BY_ALICE)

        a_world.whereabouts.enter_section(PersonBody(ALICE), _BENCH, frozenset())

        assert condition.holds(a_world.facts(), _BY_ALICE)


class TestSearchCountAtLeast:
    """SearchCountAtLeastCondition が、今いる場所で探した回数を数え、移動の途中は偽にすることを保証する。"""

    def test_counts_searches_at_the_current_spot(self) -> None:
        """広場を 2 回探した alice が広場にいれば、2 回以上で真、3 回以上で偽。"""
        a_world = _world()
        a_world.whereabouts.place(PersonBody(ALICE), _SQUARE)
        for _ in range(2):
            a_world.search_progress_at(_SQUARE.spot_id).record_search(ALICE)

        assert SearchCountAtLeastCondition(who=Actor(), count=Count(2), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )
        assert not SearchCountAtLeastCondition(who=Actor(), count=Count(3), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_searches_elsewhere_do_not_count(self) -> None:
        """広場を探したあと井戸端にいる alice は、1 回以上の条件で偽。"""
        a_world = _world()
        a_world.whereabouts.place(PersonBody(ALICE), _WELL_SIDE)
        a_world.search_progress_at(_SQUARE.spot_id).record_search(ALICE)

        assert not SearchCountAtLeastCondition(who=Actor(), count=Count(1), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_travelling_is_false(self) -> None:
        """移動の途中の alice は、0 回以上の条件でも偽。"""
        a_world = _world()
        a_world.whereabouts.place(PersonBody(ALICE), _SQUARE)
        a_world.whereabouts.start_travel(PersonBody(ALICE), Route(start=_SQUARE.spot_id, passages=(_LANE,)))

        assert not SearchCountAtLeastCondition(who=Actor(), count=Count(0), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )


class TestLifeAndBody:
    """IsDown・IsAlive・HungerAtLeast・FatigueAtLeast が facts.vitals() を読むことを保証する。"""

    def test_down_person_is_down_and_alive(self) -> None:
        """倒れた alice は、倒れている条件でも生きている条件でも真。"""
        a_world = _world()
        a_world.vitals[ALICE].take_damage(Damage(5), WorldTick(0), StruckByPerson(BOB))

        assert IsDownCondition(who=Actor(), failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)
        assert IsAliveCondition(who=Actor(), failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)

    def test_standing_person_is_not_down(self) -> None:
        """立っている alice は、倒れている条件で偽、生きている条件で真。"""
        facts = _world().facts()

        assert not IsDownCondition(who=Actor(), failure_text=NoText()).holds(facts, _BY_ALICE)
        assert IsAliveCondition(who=Actor(), failure_text=NoText()).holds(facts, _BY_ALICE)

    def test_dead_person_is_neither_down_nor_alive(self) -> None:
        """死んだ alice は、倒れている条件でも生きている条件でも偽。"""
        a_world = _world()
        _kill_alice(a_world)

        assert not IsDownCondition(who=Actor(), failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)
        assert not IsAliveCondition(who=Actor(), failure_text=NoText()).holds(a_world.facts(), _BY_ALICE)

    def test_hunger_and_fatigue_at_least(self) -> None:
        """空腹 2、疲れ 3 の alice は、空腹 2 以上と疲れ 3 以上で真、空腹 3 以上と疲れ 4 以上で偽。"""
        a_world = _world()
        for tick in (1, 2):
            a_world.vitals[ALICE].pass_time(WorldTick(tick), DeathRule(grace=Ticks(1)), _HUNGER)
        a_world.vitals[ALICE].exert(_FATIGUE)
        facts = a_world.facts()

        assert HungerAtLeastCondition(who=Actor(), value=HungerAmount(2), failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not HungerAtLeastCondition(who=Actor(), value=HungerAmount(3), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )
        assert FatigueAtLeastCondition(who=Actor(), value=FatigueAmount(3), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )
        assert not FatigueAtLeastCondition(who=Actor(), value=FatigueAmount(4), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )


class TestOutcomesAndPeople:
    """結末の条件と PeopleCountAtLeastCondition が facts.outcomes() と PeopleSelection を読むことを保証する。"""

    def test_outcome_is(self) -> None:
        """結末が死に決まった alice は、死の条件で真。まだ決まっていない bob を相手にすると偽。"""
        a_world = _world()
        a_world.outcomes.decide(ALICE, Died())
        condition = OutcomeIsCondition(who=Target(), outcome=Died(), failure_text=NoText())

        assert condition.holds(a_world.facts(), ActionAttemptForTests(actor_id=BOB, target=ALICE))
        assert not condition.holds(a_world.facts(), _ALICE_TO_BOB)

    def test_all_outcomes_decided(self) -> None:
        """3 人のうち 2 人だけ決まっていれば偽、3 人とも決まれば真。"""
        a_world = _world()
        condition = AllOutcomesDecidedCondition(failure_text=NoText())
        a_world.outcomes.decide(ALICE, Died())
        a_world.outcomes.decide(BOB, Died())
        assert not condition.holds(a_world.facts(), _BY_ALICE)

        a_world.outcomes.decide(CAROL, Died())

        assert condition.holds(a_world.facts(), _BY_ALICE)

    def test_people_count_at_least(self) -> None:
        """村人が alice と bob の 2 人なら、村人が 2 人以上の条件は真、3 人以上は偽。"""
        villagers = group("villagers", visibility=MembershipVisibility.EVERYONE)
        a_world = _world()
        a_world.membership.join(ALICE, villagers)
        a_world.membership.join(BOB, villagers)
        people = PeopleSelection(where=IsMemberCondition(who=EachPerson(), group=villagers, failure_text=NoText()))

        assert PeopleCountAtLeastCondition(people=people, count=Count(2), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )
        assert not PeopleCountAtLeastCondition(people=people, count=Count(3), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )
        assert (
            SubjectKind.EACH_PERSON
            not in PeopleCountAtLeastCondition(people=people, count=Count(2), failure_text=NoText())
            .requirements()
            .subjects
        )
