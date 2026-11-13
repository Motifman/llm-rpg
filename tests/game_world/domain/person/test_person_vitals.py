from __future__ import annotations

from collections.abc import Callable

import pytest

from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    GameWorldDomainException,
)
from ai_rpg_world.game_world.domain.exception.person_exception import (
    HitPointsDoNotMatchLifeStateException,
    PersonNotAliveException,
    PersonNotDownException,
    PersonStartsFallenException,
    StatusEffectKindRepeatedException,
)
from ai_rpg_world.game_world.domain.person import (
    Alive,
    Dead,
    Down,
    FatigueLevelChangedEvent,
    HungerLevelChangedEvent,
    NoPreviousAction,
    NoPreviousStatusEffect,
    NotBusy,
    PersonBecameBusyEvent,
    PersonDamagedEvent,
    PersonDiedEvent,
    PersonFellEvent,
    PersonHealedEvent,
    PersonRevivedEvent,
    PersonVitals,
    PersonVitalsMemento,
    Starvation,
    StatusEffect,
    StatusEffectAddedEvent,
    StatusEffectExpiredEvent,
    StatusEffectType,
    StruckByPerson,
    WorldHappening,
)
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import (
    HungerLevel,
    HungerLevelName,
    HungerRule,
    NoStarvationDamage,
)
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    FatigueAmount,
    HealAmount,
    HitPoints,
    HungerAmount,
    PersonId,
    Rate,
    Ticks,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_STRUCK = StruckByPerson(_BOB)


def _vitals(current: int = 10, maximum: int = 10) -> PersonVitals:
    vitals = PersonVitals.start(_ALICE, HitPoints(current=current, maximum=maximum))
    vitals.clear_events()
    return vitals


def _hunger(per_tick: int = 1, limit: int = 3, starvation: int | None = 2) -> HungerRule:
    return HungerRule(
        per_tick=HungerAmount(per_tick),
        limit=HungerAmount(limit),
        starvation_damage=NoStarvationDamage() if starvation is None else Damage(starvation),
        levels=(
            HungerLevel(starts_at=HungerAmount(0), name=HungerLevelName("満腹")),
            HungerLevel(starts_at=HungerAmount(2), name=HungerLevelName("空腹")),
        ),
    )


def _no_hunger() -> HungerRule:
    return _hunger(per_tick=0)


def _fatigue(per_exertion: int = 2, limit: int = 4) -> FatigueRule:
    return FatigueRule(
        per_exertion=FatigueAmount(per_exertion),
        limit=FatigueAmount(limit),
        levels=(
            FatigueLevel(starts_at=FatigueAmount(0), name=FatigueLevelName("元気")),
            FatigueLevel(starts_at=FatigueAmount(3), name=FatigueLevelName("疲れた")),
        ),
    )


def _death(grace: int = 2) -> DeathRule:
    return DeathRule(grace=Ticks(grace))


def _fallen(at: int = 5) -> PersonVitals:
    vitals = _vitals()
    vitals.take_damage(Damage(10), WorldTick(at), _STRUCK)
    vitals.clear_events()
    return vitals


def _dead() -> PersonVitals:
    vitals = _fallen(at=5)
    vitals.pass_time(WorldTick(7), _death(grace=2), _no_hunger())
    vitals.clear_events()
    return vitals


class TestStart:
    """PersonVitals.start が、受け取った HP で起きている人の体を作ることを保証する。"""

    def test_starts_alive_with_the_given_hit_points(self) -> None:
        """渡した HitPoints を持ち、Alive で始まり、行為ができる。"""
        vitals = PersonVitals.start(_ALICE, HitPoints(current=7, maximum=10))

        assert vitals.hp() == HitPoints(current=7, maximum=10)
        assert vitals.memento().life_state == Alive()
        assert vitals.can_act()

    def test_starts_without_events(self) -> None:
        """作っただけではドメインイベントをためない。"""
        vitals = PersonVitals.start(_ALICE, HitPoints(current=10, maximum=10))

        assert vitals.get_events() == []

    def test_keeps_the_person_as_its_id(self) -> None:
        """人ごとの集約として、自分の PersonId を持つ。"""
        assert PersonVitals.start(_ALICE, HitPoints(current=10, maximum=10)).person == _ALICE

    def test_zero_hit_points_raises_domain_exception(self) -> None:
        """今の HP が 0 の体は、起きている人として始められないので PersonStartsFallenException を投げる。"""
        with pytest.raises(PersonStartsFallenException):
            PersonVitals.start(_ALICE, HitPoints(current=0, maximum=10))


class TestTakeDamage:
    """take_damage が HP を減らし、0 になったら Down にすることを保証する。"""

    def test_damage_lowers_hit_points_and_reports_before_and_after(self) -> None:
        """HP 10 の人に 3 の痛手を与えると HP 7 になり、前後の HP と原因を持つ PersonDamagedEvent を 1 件ためる。"""
        vitals = _vitals()

        vitals.take_damage(Damage(3), WorldTick(5), _STRUCK)

        assert vitals.hp() == HitPoints(current=7, maximum=10)
        assert vitals.memento().life_state == Alive()
        [event] = vitals.get_events()
        assert isinstance(event, PersonDamagedEvent)
        assert (event.person, event.amount, event.hp_before, event.hp_after, event.cause) == (
            _ALICE,
            Damage(3),
            HitPoints(current=10, maximum=10),
            HitPoints(current=7, maximum=10),
            _STRUCK,
        )

    def test_hit_points_reaching_zero_makes_the_person_fall(self) -> None:
        """HP が 0 になると Down(fell_at=now, cause) になり、PersonDamagedEvent のあとに PersonFellEvent をためる。"""
        vitals = _vitals()

        vitals.take_damage(Damage(12), WorldTick(5), WorldHappening())

        assert vitals.hp() == HitPoints(current=0, maximum=10)
        assert vitals.memento().life_state == Down(fell_at=WorldTick(5), cause=WorldHappening())
        assert not vitals.can_act()
        damaged, fell = vitals.get_events()
        assert isinstance(damaged, PersonDamagedEvent)
        assert isinstance(fell, PersonFellEvent)
        assert (fell.person, fell.fell_at, fell.cause) == (_ALICE, WorldTick(5), WorldHappening())

    def test_damage_to_a_fallen_person_raises_domain_exception_without_events(self) -> None:
        """Down の人への痛手は PersonNotAliveException を投げ、イベントをためない。"""
        vitals = _fallen()

        with pytest.raises(PersonNotAliveException):
            vitals.take_damage(Damage(1), WorldTick(6), _STRUCK)
        assert vitals.get_events() == []

    def test_damage_to_a_dead_person_raises_domain_exception(self) -> None:
        """Dead の人への痛手は PersonNotAliveException を投げる。"""
        with pytest.raises(PersonNotAliveException):
            _dead().take_damage(Damage(1), WorldTick(9), _STRUCK)


class TestHeal:
    """heal が起きている人の HP を最大値まで戻すことを保証する。"""

    def test_heal_raises_hit_points_and_reports_before_and_after(self) -> None:
        """HP 4/10 の人を 3 回復すると 7 になり、前後の HP を持つ PersonHealedEvent をためる。"""
        vitals = _vitals(current=4)

        vitals.heal(HealAmount(3))

        assert vitals.hp() == HitPoints(current=7, maximum=10)
        [event] = vitals.get_events()
        assert isinstance(event, PersonHealedEvent)
        assert (event.person, event.hp_before, event.hp_after) == (
            _ALICE,
            HitPoints(current=4, maximum=10),
            HitPoints(current=7, maximum=10),
        )

    def test_heal_stops_at_maximum(self) -> None:
        """回復は最大値で止まる。"""
        vitals = _vitals(current=9)

        vitals.heal(HealAmount(5))

        assert vitals.hp() == HitPoints(current=10, maximum=10)

    def test_heal_at_full_hit_points_changes_nothing_and_raises_no_event(self) -> None:
        """HP が満タンの人を回復しても HP は変わらず、状態が変わらないのでイベントをためない。"""
        vitals = _vitals()

        vitals.heal(HealAmount(5))

        assert vitals.get_events() == []

    @pytest.mark.parametrize("make", [_fallen, _dead])
    def test_heal_on_a_person_not_alive_raises_domain_exception(self, make) -> None:
        """Down・Dead の人の回復は PersonNotAliveException を投げる (起こすのは revive)。"""
        with pytest.raises(PersonNotAliveException):
            make().heal(HealAmount(1))


class TestRevive:
    """revive が倒れた人だけを、最大 HP に率を掛けた HP で起こすことを保証する。"""

    def test_revive_wakes_a_fallen_person_with_rounded_down_hit_points(self) -> None:
        """最大 7 の倒れた人を率 0.6 で起こすと、4.2 を切り捨てた HP 4 で Alive になり、PersonRevivedEvent をためる。"""
        vitals = PersonVitals.start(_ALICE, HitPoints(current=7, maximum=7))
        vitals.take_damage(Damage(7), WorldTick(5), _STRUCK)
        vitals.clear_events()

        vitals.revive(Rate(0.6), WorldTick(6))

        assert vitals.hp() == HitPoints(current=4, maximum=7)
        assert vitals.memento().life_state == Alive()
        [event] = vitals.get_events()
        assert isinstance(event, PersonRevivedEvent)
        assert (event.person, event.revived_at, event.hp_after) == (_ALICE, WorldTick(6), HitPoints(4, 7))

    @pytest.mark.parametrize(("rate", "expected"), [(0.29, 29), (0.57, 57)])
    def test_revive_rounds_down_the_exact_product(self, rate: float, expected: int) -> None:
        """最大 100 を率 0.29 / 0.57 で起こすと、浮動小数の誤差で 1 減らさず、29 / 57 で起きる。"""
        vitals = PersonVitals.start(_ALICE, HitPoints(current=100, maximum=100))
        vitals.take_damage(Damage(100), WorldTick(5), _STRUCK)

        vitals.revive(Rate(rate), WorldTick(6))

        assert vitals.hp() == HitPoints(current=expected, maximum=100)

    def test_revive_with_zero_rate_still_wakes_with_one_hit_point(self) -> None:
        """率が 0 でも、起きたのに HP 0 にはならず HP 1 で起きる。"""
        vitals = _fallen()

        vitals.revive(Rate(0.0), WorldTick(6))

        assert vitals.hp() == HitPoints(current=1, maximum=10)

    def test_revive_on_an_alive_person_raises_domain_exception(self) -> None:
        """起きている人の revive は PersonNotDownException を投げ、イベントをためない。"""
        vitals = _vitals()

        with pytest.raises(PersonNotDownException):
            vitals.revive(Rate(0.6), WorldTick(6))
        assert vitals.get_events() == []

    def test_revive_on_a_dead_person_raises_domain_exception(self) -> None:
        """死んだ人の revive は PersonNotDownException を投げる。"""
        with pytest.raises(PersonNotDownException):
            _dead().revive(Rate(0.6), WorldTick(9))


class TestPassTimeDeath:
    """pass_time が、倒れてから DeathRule.grace が過ぎた tick に人を死なせることを保証する。"""

    def test_fallen_person_survives_before_grace_passes(self) -> None:
        """tick 5 に倒れ猶予 2 なら、tick 6 の pass_time ではまだ Down のまま。"""
        vitals = _fallen(at=5)

        vitals.pass_time(WorldTick(6), _death(grace=2), _hunger())

        assert vitals.memento().life_state == Down(fell_at=WorldTick(5), cause=_STRUCK)
        assert vitals.get_events() == []

    def test_fallen_person_dies_when_grace_has_passed(self) -> None:
        """tick 5 に倒れ猶予 2 なら、tick 7 の pass_time で Dead(died_at=7) になり PersonDiedEvent をためる。"""
        vitals = _fallen(at=5)

        vitals.pass_time(WorldTick(7), _death(grace=2), _hunger())

        assert vitals.memento().life_state == Dead(died_at=WorldTick(7))
        assert vitals.is_dead()
        [event] = vitals.get_events()
        assert isinstance(event, PersonDiedEvent)
        assert (event.person, event.died_at) == (_ALICE, WorldTick(7))

    def test_dead_person_changes_nothing_as_time_passes(self) -> None:
        """死んだ人は時が過ぎても何も変わらず、イベントをためない。"""
        vitals = _dead()

        vitals.pass_time(WorldTick(20), _death(), _hunger())

        assert vitals.memento().life_state == Dead(died_at=WorldTick(7))
        assert vitals.get_events() == []

    def test_alive_person_is_not_dead(self) -> None:
        """起きている人と倒れた人は is_dead が偽。"""
        assert not _vitals().is_dead()
        assert not _fallen().is_dead()


class TestIsDown:
    """is_down が、倒れていて死んではいない人だけを真と答えることを保証する。"""

    def test_fallen_person_is_down(self) -> None:
        """HP が 0 になって倒れた人は is_down が真。"""
        assert _fallen().is_down()

    def test_alive_person_is_not_down(self) -> None:
        """起きている人は is_down が偽。"""
        assert not _vitals().is_down()

    def test_dead_person_is_not_down(self) -> None:
        """倒れたまま猶予が過ぎて死んだ人は is_down が偽。"""
        assert not _dead().is_down()


class TestPassTimeHunger:
    """pass_time が起きている人の空腹を進め、限界のあいだ飢えの痛手を与えることを保証する。"""

    def test_hunger_level_change_raises_event_with_before_and_after(self) -> None:
        """空腹が段階の境目 (2) に達した pass_time だけ、前後の段階を持つ HungerLevelChangedEvent をためる。"""
        vitals = _vitals()
        rule = _hunger(per_tick=1)

        vitals.pass_time(WorldTick(1), _death(), rule)
        assert vitals.get_events() == []

        vitals.pass_time(WorldTick(2), _death(), rule)

        [event] = vitals.get_events()
        assert isinstance(event, HungerLevelChangedEvent)
        assert (event.person, event.level_before.name.value, event.level_after.name.value) == (
            _ALICE,
            "満腹",
            "空腹",
        )

    def test_starving_person_takes_starvation_damage_every_tick(self) -> None:
        """空腹が限界 (3) のあいだ、pass_time ごとに原因 Starvation の痛手 2 を受ける。"""
        vitals = _vitals()
        rule = _hunger(per_tick=1, limit=3, starvation=2)
        for tick in (1, 2):
            vitals.pass_time(WorldTick(tick), _death(), rule)
        vitals.clear_events()

        vitals.pass_time(WorldTick(3), _death(), rule)
        vitals.pass_time(WorldTick(4), _death(), rule)

        assert vitals.hp() == HitPoints(current=6, maximum=10)
        damaged = [e for e in vitals.get_events() if isinstance(e, PersonDamagedEvent)]
        assert [(e.amount, e.cause) for e in damaged] == [(Damage(2), Starvation()), (Damage(2), Starvation())]

    def test_hunger_stops_at_the_limit_and_raises_no_further_level_event(self) -> None:
        """限界を超えて空腹は増えず、段階が変わらないので限界のあとは HungerLevelChangedEvent を出さない。"""
        vitals = _vitals()
        rule = _hunger(per_tick=5, limit=3, starvation=None)

        vitals.pass_time(WorldTick(1), _death(), rule)
        vitals.clear_events()
        vitals.pass_time(WorldTick(2), _death(), rule)

        assert vitals.get_events() == []

    def test_hunger_beyond_the_limit_is_not_kept(self) -> None:
        """限界 3 を超えて進めても空腹は 3 で止まるので、2 食べると 1 になり満腹の段階に戻る。"""
        vitals = _vitals()
        rule = _hunger(per_tick=5, limit=3, starvation=None)
        for tick in (1, 2, 3):
            vitals.pass_time(WorldTick(tick), _death(), rule)
        vitals.clear_events()

        vitals.satisfy_hunger(HungerAmount(2), rule)

        [event] = vitals.get_events()
        assert isinstance(event, HungerLevelChangedEvent)
        assert event.level_after.name.value == "満腹"

    def test_no_starvation_damage_means_starving_does_not_hurt(self) -> None:
        """starvation_damage が NoStarvationDamage なら、限界のあいだも HP は減らない。"""
        vitals = _vitals()
        rule = _hunger(per_tick=3, limit=3, starvation=None)

        vitals.pass_time(WorldTick(1), _death(), rule)
        vitals.pass_time(WorldTick(2), _death(), rule)

        assert vitals.hp() == HitPoints(current=10, maximum=10)

    def test_starvation_can_make_the_person_fall(self) -> None:
        """飢えの痛手で HP が 0 になると、原因 Starvation で Down になる。"""
        vitals = _vitals(current=2)

        vitals.pass_time(WorldTick(1), _death(grace=5), _hunger(per_tick=3, limit=3, starvation=2))

        assert vitals.memento().life_state == Down(fell_at=WorldTick(1), cause=Starvation())

    def test_zero_grace_kills_a_person_who_starves_in_the_same_pass(self) -> None:
        """猶予 0 の世界で飢えて倒れた人は、同じ pass_time で Dead になる (倒れたらすぐ死ぬ)。"""
        vitals = _vitals(current=2)

        vitals.pass_time(WorldTick(1), _death(grace=0), _hunger(per_tick=3, limit=3, starvation=2))

        assert vitals.memento().life_state == Dead(died_at=WorldTick(1))
        assert [type(e) for e in vitals.get_events()] == [
            HungerLevelChangedEvent,
            PersonDamagedEvent,
            PersonFellEvent,
            PersonDiedEvent,
        ]

    def test_hunger_does_not_advance_while_fallen(self) -> None:
        """倒れているあいだは空腹が進まないので、起こしたあとも段階は変わっていない。"""
        vitals = _fallen(at=0)
        rule = _hunger(per_tick=1, limit=3)
        for tick in (1, 2, 3):
            vitals.pass_time(WorldTick(tick), _death(grace=10), rule)
        vitals.revive(Rate(1.0), WorldTick(4))
        vitals.clear_events()

        vitals.pass_time(WorldTick(5), _death(grace=10), rule)

        assert vitals.get_events() == []


class TestSatisfyHunger:
    """satisfy_hunger が空腹を減らし、段階が変わったときだけ知らせることを保証する。"""

    def test_eating_lowers_the_hunger_level(self) -> None:
        """空腹の段階の人が食べて満腹の段階に戻ると、HungerLevelChangedEvent をためる。"""
        vitals = _vitals()
        rule = _hunger(per_tick=2, limit=3, starvation=None)
        vitals.pass_time(WorldTick(1), _death(), rule)
        vitals.clear_events()

        vitals.satisfy_hunger(HungerAmount(5), rule)

        [event] = vitals.get_events()
        assert isinstance(event, HungerLevelChangedEvent)
        assert (event.level_before.name.value, event.level_after.name.value) == ("空腹", "満腹")

    def test_eating_without_level_change_raises_no_event(self) -> None:
        """段階が変わらない食事はイベントをためない。"""
        vitals = _vitals()
        rule = _hunger(per_tick=1)
        vitals.pass_time(WorldTick(1), _death(), rule)
        vitals.clear_events()

        vitals.satisfy_hunger(HungerAmount(1), rule)

        assert vitals.get_events() == []

    @pytest.mark.parametrize("make", [_fallen, _dead])
    def test_eating_while_not_alive_raises_domain_exception(self, make) -> None:
        """Down・Dead の人は食べられず、PersonNotAliveException を投げる。"""
        with pytest.raises(PersonNotAliveException):
            make().satisfy_hunger(HungerAmount(1), _hunger())


class TestFatigue:
    """exert と rest が疲れを上下させ、段階が変わったときだけ知らせることを保証する。"""

    def test_exertion_crossing_a_level_raises_event(self) -> None:
        """疲れ 0 から 2 ずつ体を使い、境目 3 を越えた 2 回目だけ FatigueLevelChangedEvent をためる。"""
        vitals = _vitals()
        rule = _fatigue(per_exertion=2, limit=4)

        vitals.exert(rule)
        assert vitals.get_events() == []
        vitals.exert(rule)

        [event] = vitals.get_events()
        assert isinstance(event, FatigueLevelChangedEvent)
        assert (event.person, event.level_before.name.value, event.level_after.name.value) == (
            _ALICE,
            "元気",
            "疲れた",
        )

    def test_fatigue_stops_at_the_limit(self) -> None:
        """疲れは limit で止まり、limit に達すると fatigue_reached_limit が真になる。"""
        vitals = _vitals()
        rule = _fatigue(per_exertion=3, limit=4)

        vitals.exert(rule)
        assert not vitals.fatigue_reached_limit(rule)
        vitals.exert(rule)
        vitals.exert(rule)

        assert vitals.fatigue_reached_limit(rule)
        vitals.rest(FatigueAmount(1), rule)
        assert not vitals.fatigue_reached_limit(rule)

    def test_rest_lowering_the_level_raises_event(self) -> None:
        """疲れた段階の人が休んで元気の段階に戻ると FatigueLevelChangedEvent をためる。"""
        vitals = _vitals()
        rule = _fatigue(per_exertion=4, limit=4)
        vitals.exert(rule)
        vitals.clear_events()

        vitals.rest(FatigueAmount(10), rule)

        [event] = vitals.get_events()
        assert isinstance(event, FatigueLevelChangedEvent)
        assert (event.level_before.name.value, event.level_after.name.value) == ("疲れた", "元気")

    def test_rest_without_level_change_raises_no_event(self) -> None:
        """段階が変わらない休みはイベントをためない。"""
        vitals = _vitals()
        rule = _fatigue(per_exertion=2, limit=4)
        vitals.exert(rule)
        vitals.clear_events()

        vitals.rest(FatigueAmount(1), rule)

        assert vitals.get_events() == []

    @pytest.mark.parametrize("make", [_fallen, _dead])
    def test_exert_while_not_alive_raises_domain_exception(self, make) -> None:
        """Down・Dead の人は体を使えず、PersonNotAliveException を投げる。"""
        with pytest.raises(PersonNotAliveException):
            make().exert(_fatigue())

    @pytest.mark.parametrize("make", [_fallen, _dead])
    def test_rest_while_not_alive_raises_domain_exception(self, make) -> None:
        """Down・Dead の人は休めず、PersonNotAliveException を投げる。"""
        with pytest.raises(PersonNotAliveException):
            make().rest(FatigueAmount(1), _fatigue())


class TestBusy:
    """start_action と is_busy が、行為を行っているあいだを表すことを保証する。"""

    def test_person_is_busy_until_the_given_tick(self) -> None:
        """tick 7 まで行っているなら、tick 6 では is_busy が真、tick 7 では偽。"""
        vitals = _vitals()

        vitals.start_action(WorldTick(7))

        assert vitals.is_busy(WorldTick(6))
        assert not vitals.is_busy(WorldTick(7))

    def test_start_action_raises_event(self) -> None:
        """初めての start_action は、いつまで行っているかと、前の行為が無かったことを持つ PersonBecameBusyEvent をためる。"""
        vitals = _vitals()

        vitals.start_action(WorldTick(7))

        [event] = vitals.get_events()
        assert isinstance(event, PersonBecameBusyEvent)
        assert (event.person, event.until, event.previous_until) == (_ALICE, WorldTick(7), NoPreviousAction())

    def test_starting_again_replaces_the_end_and_reports_the_previous_end(self) -> None:
        """もう一度 start_action を呼ぶと終わりの tick を置き換え、イベントに前の終わりを持たせる。"""
        vitals = _vitals()
        vitals.start_action(WorldTick(7))
        vitals.clear_events()

        vitals.start_action(WorldTick(4))

        assert not vitals.is_busy(WorldTick(5))
        [event] = vitals.get_events()
        assert isinstance(event, PersonBecameBusyEvent)
        assert (event.until, event.previous_until) == (WorldTick(4), WorldTick(7))

    def test_person_who_never_acted_is_not_busy(self) -> None:
        """一度も行為を始めていない人は is_busy が偽。"""
        assert not _vitals().is_busy(WorldTick(0))

    @pytest.mark.parametrize("make", [_fallen, _dead])
    def test_start_action_while_not_alive_raises_domain_exception(self, make) -> None:
        """Down・Dead の人は行為を始められず、PersonNotAliveException を投げる。"""
        with pytest.raises(PersonNotAliveException):
            make().start_action(WorldTick(20))


class TestStatusEffects:
    """状態効果が種類ごとに 1 つで、期限が来たら外れることを保証する。"""

    _BLEEDING = StatusEffectType("bleeding")

    def test_adding_an_effect_raises_event_without_previous(self) -> None:
        """かかっていない種類を付けると、前の効果が無いことを示す StatusEffectAddedEvent をためる。"""
        vitals = _vitals()
        effect = StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(10))

        vitals.add_status_effect(effect)

        [event] = vitals.get_events()
        assert isinstance(event, StatusEffectAddedEvent)
        assert (event.person, event.effect, event.replaced) == (_ALICE, effect, NoPreviousStatusEffect())

    def test_adding_the_same_kind_replaces_the_expiry(self) -> None:
        """同じ種類をもう一度付けると期限を置き換え、イベントに置き換えた前の効果を持つ。前の期限では外れない。"""
        vitals = _vitals()
        first = StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(5))
        second = StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(10))
        vitals.add_status_effect(first)
        vitals.clear_events()

        vitals.add_status_effect(second)
        [added] = vitals.get_events()
        vitals.clear_events()
        vitals.remove_expired_status_effects(WorldTick(5))

        assert isinstance(added, StatusEffectAddedEvent)
        assert added.replaced == first
        assert vitals.get_events() == []

    def test_expired_effects_are_removed_with_event(self) -> None:
        """期限の tick に達した効果は外れて StatusEffectExpiredEvent をため、期限前の効果は残る。"""
        vitals = _vitals()
        expiring = StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(5))
        lasting = StatusEffect(kind=StatusEffectType("poison"), expires_at=WorldTick(9))
        vitals.add_status_effect(expiring)
        vitals.add_status_effect(lasting)
        vitals.clear_events()

        vitals.remove_expired_status_effects(WorldTick(5))

        [event] = vitals.get_events()
        assert isinstance(event, StatusEffectExpiredEvent)
        assert (event.person, event.effect) == (_ALICE, expiring)

    def test_removed_effect_does_not_expire_again(self) -> None:
        """一度外れた効果は、あとの tick でもう一度外れたことにならず、期限前の効果も残る。"""
        vitals = _vitals()
        vitals.add_status_effect(StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(5)))
        vitals.add_status_effect(StatusEffect(kind=StatusEffectType("poison"), expires_at=WorldTick(9)))
        vitals.remove_expired_status_effects(WorldTick(5))
        vitals.clear_events()

        vitals.remove_expired_status_effects(WorldTick(8))

        assert vitals.get_events() == []

    def test_effects_expire_on_a_fallen_person(self) -> None:
        """期限で外すのは時の経過なので、倒れた人の効果も期限の tick に外れて StatusEffectExpiredEvent をためる。"""
        vitals = _vitals()
        effect = StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(8))
        vitals.add_status_effect(effect)
        vitals.take_damage(Damage(10), WorldTick(6), _STRUCK)
        vitals.clear_events()

        vitals.remove_expired_status_effects(WorldTick(8))

        [event] = vitals.get_events()
        assert isinstance(event, StatusEffectExpiredEvent)
        assert event.effect == effect

    def test_effects_expire_on_a_dead_person(self) -> None:
        """死んだ人の効果も期限の tick に外れ、StatusEffectExpiredEvent をためる。"""
        vitals = _vitals()
        effect = StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(20))
        vitals.add_status_effect(effect)
        vitals.take_damage(Damage(10), WorldTick(5), _STRUCK)
        vitals.pass_time(WorldTick(7), _death(grace=2), _no_hunger())
        vitals.clear_events()

        vitals.remove_expired_status_effects(WorldTick(20))

        [event] = vitals.get_events()
        assert isinstance(event, StatusEffectExpiredEvent)
        assert event.effect == effect

    @pytest.mark.parametrize("make", [_fallen, _dead])
    def test_adding_to_a_person_not_alive_raises_domain_exception(self, make) -> None:
        """Down・Dead の人には状態効果を付けられず、PersonNotAliveException を投げる。"""
        with pytest.raises(PersonNotAliveException):
            make().add_status_effect(StatusEffect(kind=self._BLEEDING, expires_at=WorldTick(30)))

    def test_blank_status_effect_type_raises_domain_exception(self) -> None:
        """空の種類名の StatusEffectType は GameWorldDomainException を投げる。"""
        with pytest.raises(GameWorldDomainException):
            StatusEffectType(" ")


class TestRefusalsLeaveStateUnchanged:
    """断った操作が体の状態を変えないことを保証する。"""

    def test_refused_damage_leaves_the_fallen_state(self) -> None:
        """倒れた人への痛手を断ったあとも、倒れた tick と原因は変わらない。"""
        vitals = _fallen(at=5)

        with pytest.raises(PersonNotAliveException):
            vitals.take_damage(Damage(1), WorldTick(6), WorldHappening())

        assert vitals.memento().life_state == Down(fell_at=WorldTick(5), cause=_STRUCK)


class TestHungerAndFatigueReadings:
    """PersonVitals.hunger / fatigue が、いまの空腹と疲れの量を答えることを保証する。"""

    def test_start_with_no_hunger_and_no_fatigue(self) -> None:
        """始めたばかりの人の空腹と疲れは、どちらも 0。"""
        vitals = _vitals()

        assert vitals.hunger() == HungerAmount(0)
        assert vitals.fatigue() == FatigueAmount(0)

    def test_hunger_grows_as_time_passes(self) -> None:
        """1 tick に 1 ずつ空腹が進む規則で 2 tick 過ごすと、空腹は 2。"""
        vitals = _vitals()

        vitals.pass_time(WorldTick(1), _death(), _hunger(per_tick=1))
        vitals.pass_time(WorldTick(2), _death(), _hunger(per_tick=1))

        assert vitals.hunger() == HungerAmount(2)

    def test_fatigue_grows_with_exertion(self) -> None:
        """1 回体を使うと 2 疲れる規則で 1 回体を使うと、疲れは 2。"""
        vitals = _vitals()

        vitals.exert(_fatigue(per_exertion=2))

        assert vitals.fatigue() == FatigueAmount(2)


class TestOccupantInWorld:
    """PersonVitals.occupant_in_world が、体の生死と去った人が動く世界かで、世界の中で居場所を持つ主を答えることを保証する。"""

    @pytest.mark.parametrize("make", [_vitals, _fallen])
    @pytest.mark.parametrize("departed_persons_act", [True, False])
    def test_living_or_fallen_person_is_body(
        self, make: Callable[[], PersonVitals], departed_persons_act: bool
    ) -> None:
        """起きている人と倒れた人は、去った人が動く世界でも動かない世界でも PersonBody。"""
        assert make().occupant_in_world(departed_persons_act) == PersonBody(_ALICE)

    def test_dead_person_is_departed_when_departed_persons_act(self) -> None:
        """体が死んだ人は、去った人が動く世界では DepartedPerson。"""
        assert _dead().occupant_in_world(True) == DepartedPerson(_ALICE)

    def test_dead_person_is_body_when_departed_persons_do_not_act(self) -> None:
        """体が死んだ人は、去った人が動かない世界では PersonBody。"""
        assert _dead().occupant_in_world(False) == PersonBody(_ALICE)


_DESIGN = compose_world(
    nouns(spots=(spot("beach"),), characters=(character("alice", "beach"), character("bob", "beach")))
)
_POISONED = StatusEffectType("毒")


def _memento(
    person: PersonId = _ALICE,
    hp: int = 10,
    life_state: Alive | Down | Dead = Alive(),
    status_effects: frozenset[StatusEffect] = frozenset(),
) -> PersonVitalsMemento:
    return PersonVitalsMemento(
        person=person,
        hp=HitPoints(current=hp, maximum=10),
        life_state=life_state,
        hunger=HungerAmount(0),
        fatigue=FatigueAmount(0),
        status_effects=status_effects,
        busy_until=NotBusy(),
    )


class TestPersonVitalsMemento:
    """PersonVitals を memento から作り直すと、HP・生死・空腹・疲れ・状態異常・手の塞がりが元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_fallen_person_is_down_by_the_same_cause(self) -> None:
        """tick 5 に bob に殴られて倒れた alice を作り直すと、tick 5 に bob に殴られて倒れたままで、動けない。"""
        rebuilt = rebuilt_from_memento(_fallen(at=5), _DESIGN)

        assert rebuilt.memento().life_state == Down(fell_at=WorldTick(5), cause=_STRUCK)
        assert not rebuilt.can_act()

    def test_rebuilt_dead_person_stays_dead(self) -> None:
        """死んだ alice を作り直すと、死んだときの tick を持ったまま死んでいる。"""
        rebuilt = rebuilt_from_memento(_dead(), _DESIGN)

        assert rebuilt.memento().life_state == Dead(died_at=WorldTick(7))

    def test_rebuilt_vitals_answer_like_the_original(self) -> None:
        """傷を負い、空腹と疲れがたまり、毒にかかり、tick 9 まで手が塞がった alice を作り直すと、memento も問い合わせの答えも元と同じ。"""
        vitals = _vitals()
        vitals.take_damage(Damage(3), WorldTick(1), _STRUCK)
        vitals.pass_time(WorldTick(2), _death(), _hunger())
        vitals.exert(_fatigue())
        vitals.add_status_effect(StatusEffect(_POISONED, expires_at=WorldTick(4)))
        vitals.start_action(until=WorldTick(9))

        rebuilt = rebuilt_from_memento(vitals, _DESIGN)

        assert rebuilt.memento() == vitals.memento()
        assert rebuilt.memento() != _vitals().memento()
        assert rebuilt.person == _ALICE
        assert rebuilt.hp() == HitPoints(current=7, maximum=10)
        assert rebuilt.hunger() == HungerAmount(1)
        assert rebuilt.fatigue() == FatigueAmount(2)
        assert rebuilt.is_busy(WorldTick(8))
        assert not rebuilt.is_busy(WorldTick(9))

    def test_rebuilt_status_effect_expires_at_the_same_tick(self) -> None:
        """tick 4 に切れる毒にかかった alice を作り直してから tick 4 で切れたものを外すと、同じ毒の切れたイベントが出る。"""
        vitals = _vitals()
        poison = StatusEffect(_POISONED, expires_at=WorldTick(4))
        vitals.add_status_effect(poison)
        rebuilt = rebuilt_from_memento(vitals, _DESIGN)

        rebuilt.remove_expired_status_effects(WorldTick(4))

        assert [type(e) for e in rebuilt.get_events()] == [StatusEffectExpiredEvent]
        assert rebuilt.get_events()[0].effect == poison

    def test_rebuilding_records_no_event(self) -> None:
        """傷を負って倒れたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        vitals = _vitals()
        vitals.take_damage(Damage(10), WorldTick(1), _STRUCK)

        assert rebuilt_from_memento(vitals, _DESIGN).get_events() == []


class TestPersonVitalsMementoRefusals:
    """PersonVitals の memento が、宣言に無い人や同じ状態異常の重なりを持つとき、作り直しを断ることを保証する。"""

    def test_person_not_declared_is_refused(self) -> None:
        """宣言に無い carol の memento から作り直すと、UndeclaredNounException を投げる。"""
        with pytest.raises(UndeclaredNounException):
            PersonVitals.from_memento(_memento(person=PersonId("carol")), _DESIGN)

    def test_fall_cause_by_undeclared_person_is_refused(self) -> None:
        """宣言に無い carol に殴られて倒れている memento から作り直すと、UndeclaredNounException を投げる。"""
        fallen = Down(fell_at=WorldTick(1), cause=StruckByPerson(PersonId("carol")))

        with pytest.raises(UndeclaredNounException):
            PersonVitals.from_memento(_memento(hp=0, life_state=fallen), _DESIGN)

    def test_alive_with_zero_hit_points_is_refused(self) -> None:
        """HP 0 で起きている alice の memento から作り直すと、HitPointsDoNotMatchLifeStateException を投げる。"""
        with pytest.raises(HitPointsDoNotMatchLifeStateException):
            PersonVitals.from_memento(_memento(hp=0, life_state=Alive()), _DESIGN)

    def test_down_with_hit_points_left_is_refused(self) -> None:
        """HP が 3 残ったまま倒れている alice の memento から作り直すと、HitPointsDoNotMatchLifeStateException を投げる。"""
        fallen = Down(fell_at=WorldTick(1), cause=_STRUCK)

        with pytest.raises(HitPointsDoNotMatchLifeStateException):
            PersonVitals.from_memento(_memento(hp=3, life_state=fallen), _DESIGN)

    def test_dead_with_hit_points_left_is_refused(self) -> None:
        """HP が 3 残ったまま死んでいる alice の memento から作り直すと、HitPointsDoNotMatchLifeStateException を投げる。"""
        with pytest.raises(HitPointsDoNotMatchLifeStateException):
            PersonVitals.from_memento(_memento(hp=3, life_state=Dead(died_at=WorldTick(7))), _DESIGN)

    def test_constructing_with_same_status_effect_kind_twice_is_refused(self) -> None:
        """切れる tick だけが違う毒を 2 つ渡して PersonVitals を作ると、StatusEffectKindRepeatedException を投げる。"""
        poisons = frozenset(
            {StatusEffect(_POISONED, expires_at=WorldTick(4)), StatusEffect(_POISONED, expires_at=WorldTick(6))}
        )

        with pytest.raises(StatusEffectKindRepeatedException):
            PersonVitals(
                _ALICE,
                HitPoints(current=10, maximum=10),
                Alive(),
                HungerAmount(0),
                FatigueAmount(0),
                poisons,
                NotBusy(),
            )

    def test_same_status_effect_kind_twice_is_refused(self) -> None:
        """切れる tick だけが違う毒を 2 つ持つ memento から作り直すと、操作が断るのと同じ StatusEffectKindRepeatedException を投げる。"""
        memento = _memento(
            status_effects=frozenset(
                {StatusEffect(_POISONED, expires_at=WorldTick(4)), StatusEffect(_POISONED, expires_at=WorldTick(6))}
            )
        )

        with pytest.raises(StatusEffectKindRepeatedException):
            PersonVitals.from_memento(memento, _DESIGN)
