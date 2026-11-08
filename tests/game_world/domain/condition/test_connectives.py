from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.connectives import (
    AllOfCondition,
    AnyOfCondition,
    ForEveryoneCondition,
    ForSomeoneCondition,
    NotCondition,
)
from ai_rpg_world.game_world.domain.condition.membership_condition import IsMemberCondition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.subject import Actor, EachPerson, Subject, SubjectKind, Target
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import MembershipVisibility
from ai_rpg_world.game_world.domain.exception.condition_exception import UnknownPersonPlaceholderException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Probability, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.condition._builders import ALICE, BOB, CAROL, group, text, world
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)
_ROOT = ConditionPath.root()
_VILLAGERS = group("villagers", visibility=MembershipVisibility.EVERYONE)
_WOLVES = group("wolves", visibility=MembershipVisibility.NOBODY, grouping_id="role")


def _true() -> TickAtLeastCondition:
    return TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText())


def _false(failure_text: TextWithUnassignedPeople | NoText = NoText()) -> TickAtLeastCondition:
    return TickAtLeastCondition(tick=WorldTick(5), failure_text=failure_text)


def _everyone() -> PeopleSelection:
    return PeopleSelection(where=_true())


def _villager(failure_text: TextWithUnassignedPeople | NoText = NoText()) -> IsMemberCondition:
    return IsMemberCondition(who=EachPerson(), group=_VILLAGERS, failure_text=failure_text)


class TestAllOfFailureReason:
    """AllOfCondition が、偽になった子の位置と、いちばん内側の文を返すことを保証する。"""

    def test_child_without_text_is_filled_with_all_of_text_about_actor(self) -> None:
        """2 番目の子が文を持たずに偽になると、位置 [1] と、AllOf の failure_text の {actor} に行う人を当てた文を返す。"""
        condition = AllOfCondition(children=(_true(), _false()), failure_text=text("{actor}にはまだ早い"))

        reason = condition.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(
            failed_part=_ROOT.under(1), text=text("{actor}にはまだ早い").about({"actor": ALICE})
        )

    def test_child_text_wins_over_parent_text(self) -> None:
        """偽になった子と AllOf の両方に文があれば、子の文を返す。"""
        condition = AllOfCondition(children=(_false(text("夜明けを待て")),), failure_text=text("{actor}にはまだ早い"))

        reason = condition.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT.under(0), text=text("夜明けを待て").about({}))

    def test_no_text_anywhere_returns_no_text(self) -> None:
        """子にも AllOf にも文が無ければ NoText を返し、さらに外の親が埋める。"""
        condition = AllOfCondition(children=(_false(),), failure_text=NoText())

        reason = condition.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT.under(0), text=NoText())

    def test_grandparent_fills_when_parent_has_no_text(self) -> None:
        """入れ子の AllOf で、子と中の AllOf に文が無ければ、外の AllOf の文で埋め、位置は外の番号から並ぶ。"""
        inner = AllOfCondition(children=(_true(), _false()), failure_text=NoText())
        outer = AllOfCondition(children=(_true(), inner), failure_text=text("まだだ"))

        reason = outer.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT.under(1).under(1), text=text("まだだ").about({}))

    def test_all_children_true_gives_no_reason(self) -> None:
        """子がすべて真なら holds は真で、failure_reason は None。"""
        condition = AllOfCondition(children=(_true(), _true()), failure_text=NoText())

        assert condition.holds(world().facts(), _BY_ALICE)
        assert condition.failure_reason(world().facts(), _BY_ALICE) is None

    def test_placeholder_that_is_not_a_subject_kind_is_refused(self) -> None:
        """failure_text に主語の種類名でないプレースホルダー ({alice}) があれば、文を作るときに UnknownPersonPlaceholderException を投げる。"""
        condition = AllOfCondition(children=(_false(),), failure_text=text("{alice}にはまだ早い"))

        with pytest.raises(UnknownPersonPlaceholderException):
            condition.failure_reason(world().facts(), _BY_ALICE)


class TestAllOfDrawsChanceSeparately:
    """AllOfCondition の中の ChanceCondition が、それぞれ別に偶然を引くことを保証する。"""

    def test_two_chances_draw_two_fractions(self) -> None:
        """AllOf(Chance(0.5), Chance(0.5)) に 0.2、0.7 の順で値を並べると、1 つ目は真、2 つ目は偽で、AllOf は偽。"""
        chance = ChanceCondition(probability=Probability(0.5), failure_text=NoText())
        condition = AllOfCondition(children=(chance, chance), failure_text=NoText())

        assert not condition.holds(world(fractions=(0.2, 0.7)).facts(), _BY_ALICE)

    def test_failure_reason_points_at_the_second_chance(self) -> None:
        """同じ並び 0.2、0.7 で failure_reason を求めると、2 つ目の Chance の位置 [1] を返す。"""
        chance = ChanceCondition(probability=Probability(0.5), failure_text=NoText())
        condition = AllOfCondition(children=(chance, chance), failure_text=NoText())

        reason = condition.failure_reason(world(fractions=(0.2, 0.7)).facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT.under(1), text=NoText())

    def test_stops_drawing_after_the_first_false_child(self) -> None:
        """1 つ目の Chance が 0.7 で偽になると、2 つ目は引かない。値を 1 つしか並べなくても尽きない。"""
        chance = ChanceCondition(probability=Probability(0.5), failure_text=NoText())
        condition = AllOfCondition(children=(chance, chance), failure_text=NoText())

        assert not condition.holds(world(fractions=(0.7,)).facts(), _BY_ALICE)
        assert condition.failure_reason(world(fractions=(0.7,)).facts(), _BY_ALICE) == FailureReason(
            failed_part=_ROOT.under(0), text=NoText()
        )


class TestAnyOf:
    """AnyOfCondition が、どれかの子が真なら真になり、偽なら自分の位置と自分の文を返すことを保証する。"""

    def test_one_true_child_is_enough(self) -> None:
        """偽の子と真の子が 1 つずつなら、holds は真で failure_reason は None。"""
        condition = AnyOfCondition(children=(_false(), _true()), failure_text=NoText())

        assert condition.holds(world().facts(), _BY_ALICE)
        assert condition.failure_reason(world().facts(), _BY_ALICE) is None

    def test_all_false_returns_own_position_and_own_text(self) -> None:
        """子がすべて偽なら、子の文は使わず、AnyOf 自身の位置と AnyOf の文を返す。"""
        condition = AnyOfCondition(
            children=(_false(text("夜明けを待て")), _false()), failure_text=text("{actor}には何も手がない")
        )

        reason = condition.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT, text=text("{actor}には何も手がない").about({"actor": ALICE}))


class TestNot:
    """NotCondition が子の真偽を反転し、偽なら自分の位置と自分の文を返すことを保証する。"""

    def test_false_child_makes_not_true(self) -> None:
        """子が偽なら、holds は真で failure_reason は None。"""
        condition = NotCondition(child=_false(), failure_text=NoText())

        assert condition.holds(world().facts(), _BY_ALICE)
        assert condition.failure_reason(world().facts(), _BY_ALICE) is None

    def test_true_child_returns_own_position_and_own_text(self) -> None:
        """子が真なら、Not 自身の位置と Not の文を返す。"""
        condition = NotCondition(child=_true(), failure_text=text("もう遅い"))

        reason = condition.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT, text=text("もう遅い").about({}))


class TestForEveryone:
    """ForEveryoneCondition が、選ばれた人を 1 人ずつ EachPerson として子に渡すことを保証する。"""

    def test_each_person_points_at_each_selected_person(self) -> None:
        """全員から選び、alice と bob だけが村人なら、子の文の {each_person} は村人でない carol を指し、位置は [0]。"""
        a_world = world()
        a_world.membership.join(ALICE, _VILLAGERS)
        a_world.membership.join(BOB, _VILLAGERS)
        condition = ForEveryoneCondition(
            people=_everyone(), condition=_villager(text("{each_person}は村人ではない")), failure_text=NoText()
        )

        reason = condition.failure_reason(a_world.facts(), _BY_ALICE)

        assert reason == FailureReason(
            failed_part=_ROOT.under(0), text=text("{each_person}は村人ではない").about({"each_person": CAROL})
        )

    def test_everyone_satisfying_makes_it_true(self) -> None:
        """選ばれた全員が村人なら、holds は真で failure_reason は None。"""
        a_world = world()
        for person in (ALICE, BOB, CAROL):
            a_world.membership.join(person, _VILLAGERS)
        condition = ForEveryoneCondition(people=_everyone(), condition=_villager(), failure_text=NoText())

        assert condition.holds(a_world.facts(), _BY_ALICE)
        assert condition.failure_reason(a_world.facts(), _BY_ALICE) is None

    def test_own_text_is_about_the_first_failing_person(self) -> None:
        """子が文を持たなければ、ForEveryone の文の {each_person} に、facts.people() の順で最初に偽になった人を当てる。"""
        a_world = world()
        a_world.membership.join(ALICE, _VILLAGERS)
        condition = ForEveryoneCondition(
            people=_everyone(), condition=_villager(), failure_text=text("{each_person}がまだだ")
        )

        reason = condition.failure_reason(a_world.facts(), _BY_ALICE)

        assert reason == FailureReason(
            failed_part=_ROOT.under(0), text=text("{each_person}がまだだ").about({"each_person": BOB})
        )

    def test_each_person_does_not_leak_into_requirements(self) -> None:
        """子と自分の文が EachPerson を使っても、requirements() に EACH_PERSON は出ない。"""
        condition = ForEveryoneCondition(
            people=_everyone(), condition=_villager(), failure_text=text("{each_person}がまだだ")
        )

        assert SubjectKind.EACH_PERSON not in condition.requirements().subjects


class TestForSomeone:
    """ForSomeoneCondition が、選ばれた誰かが子を満たせば真になり、偽なら自分の位置と自分の文を返すことを保証する。"""

    def test_one_satisfying_person_is_enough(self) -> None:
        """carol だけが村人でも、holds は真で failure_reason は None。"""
        a_world = world()
        a_world.membership.join(CAROL, _VILLAGERS)
        condition = ForSomeoneCondition(people=_everyone(), condition=_villager(), failure_text=NoText())

        assert condition.holds(a_world.facts(), _BY_ALICE)
        assert condition.failure_reason(a_world.facts(), _BY_ALICE) is None

    def test_nobody_satisfying_returns_own_position_and_own_text(self) -> None:
        """誰も村人でなければ、子の文は使わず、ForSomeone 自身の位置と、{actor} に行う人を当てた文を返す。"""
        condition = ForSomeoneCondition(
            people=_everyone(),
            condition=_villager(text("{each_person}は村人ではない")),
            failure_text=text("{actor}の仲間はいない"),
        )

        reason = condition.failure_reason(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT, text=text("{actor}の仲間はいない").about({"actor": ALICE}))

    def test_empty_selection_is_false(self) -> None:
        """誰も選ばれなければ偽で、ForSomeone 自身の位置を返す。"""
        condition = ForSomeoneCondition(
            people=PeopleSelection(where=_false()), condition=_true(), failure_text=NoText()
        )

        assert condition.failure_reason(world().facts(), _BY_ALICE) == FailureReason(failed_part=_ROOT, text=NoText())


class TestRequirementsOfConnectives:
    """つなぎの requirements() が、子と自分の文のプレースホルダーの要求を合わせることを保証する。"""

    def test_children_and_placeholders_are_combined(self) -> None:
        """子が Actor を、AllOf の文が {target} を使うと、ACTOR と TARGET を要る。"""
        child = IsMemberCondition(who=Actor(), group=_VILLAGERS, failure_text=NoText())
        condition = AllOfCondition(children=(child,), failure_text=text("{target}とは組めない"))

        assert condition.requirements().subjects == frozenset({SubjectKind.ACTOR, SubjectKind.TARGET})

    def test_chance_inside_is_reported(self) -> None:
        """Not の中に Chance があれば uses_chance が真。"""
        condition = NotCondition(
            child=ChanceCondition(probability=Probability(0.5), failure_text=NoText()), failure_text=NoText()
        )

        assert condition.requirements().uses_chance


class TestHiddenFailureThroughConnectives:
    """子の HiddenFailure が、つなぎを通っても伏せられたまま外へ出ることを保証する。"""

    def _wolf(self, who: Subject) -> IsMemberCondition:
        return IsMemberCondition(who=who, group=_WOLVES, failure_text=text("狼ではない"))

    def test_all_of_keeps_hidden_failure_with_its_position(self) -> None:
        """AllOf の 2 番目の子が知りえない所属で偽になると、文の無い HiddenFailure を位置 [1] で返す。"""
        condition = AllOfCondition(children=(_true(), self._wolf(Target())), failure_text=text("だめだ"))

        reason = condition.failure_reason(world().facts(), ActionAttemptForTests(actor_id=ALICE, target=BOB))

        assert reason == HiddenFailure(failed_part=_ROOT.under(1))

    def test_any_of_with_a_hidden_child_is_hidden(self) -> None:
        """AnyOf の子がすべて偽で、そのうち 1 つが HiddenFailure なら、AnyOf 自身の位置の HiddenFailure を返す。"""
        condition = AnyOfCondition(children=(_false(), self._wolf(Target())), failure_text=text("だめだ"))

        reason = condition.failure_reason(world().facts(), ActionAttemptForTests(actor_id=ALICE, target=BOB))

        assert reason == HiddenFailure(failed_part=_ROOT)

    def test_for_someone_with_a_hidden_child_is_hidden(self) -> None:
        """誰も狼でなく、狼の所属が行う人に知りえなければ、ForSomeone 自身の位置の HiddenFailure を返す。"""
        condition = ForSomeoneCondition(people=_everyone(), condition=self._wolf(EachPerson()), failure_text=NoText())

        assert condition.failure_reason(world().facts(), _BY_ALICE) == HiddenFailure(failed_part=_ROOT)

    def test_for_everyone_keeps_hidden_failure_under_its_child(self) -> None:
        """全員が狼でなく、所属が知りえなければ、ForEveryone は位置 [0] の HiddenFailure を返す。"""
        condition = ForEveryoneCondition(people=_everyone(), condition=self._wolf(EachPerson()), failure_text=NoText())

        assert condition.failure_reason(world().facts(), _BY_ALICE) == HiddenFailure(failed_part=_ROOT.under(0))

    def test_not_is_not_hidden(self) -> None:
        """Not は子が真になった理由を知らないので、伏せずに Not 自身の文を返す。"""
        a_world = world()
        a_world.membership.join(BOB, _WOLVES)
        condition = NotCondition(child=self._wolf(Target()), failure_text=text("相手を選べ"))

        reason = condition.failure_reason(a_world.facts(), ActionAttemptForTests(actor_id=ALICE, target=BOB))

        assert reason == FailureReason(failed_part=_ROOT, text=text("相手を選べ").about({}))

    def test_happening_trigger_does_not_hide(self) -> None:
        """出来事のきっかけでは行う人がいないので、知りえない所属で偽になっても、伏せずに文を返す。"""
        condition = ForSomeoneCondition(people=_everyone(), condition=self._wolf(EachPerson()), failure_text=NoText())
        happening = HappeningFired(HappeningForTests(HappeningId("dawn")))

        assert condition.failure_reason(world().facts(), happening) == FailureReason(failed_part=_ROOT, text=NoText())
