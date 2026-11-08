from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition, FlagsRaisedAtLeastCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.value_object import Count, DescriptionText, FlagId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.condition._builders import ALICE, text, world
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)
_DAWN = HappeningFired(HappeningForTests(HappeningId("dawn")))


def _flag(flag_id: str, *, initially_raised: bool = False) -> FlagDeclaration:
    return FlagDeclaration(
        flag_id=FlagId(flag_id), meaning=DescriptionText(f"{flag_id}の旗"), initially_raised=initially_raised
    )


_RED_KEY = _flag("red_key_found")
_BLUE_KEY = _flag("blue_key_found")
_GREEN_KEY = _flag("green_key_found", initially_raised=True)


def _with_raised(*flags: FlagDeclaration) -> WorldInMemory:
    a_world = world()
    for flag in flags:
        a_world.flags.raise_flag(flag, _DAWN)
    return a_world


class TestFlagIsRaisedCondition:
    """FlagIsRaisedCondition が、世界の旗が今立っているかで真偽を決めることを保証する。"""

    def test_holds_only_while_the_flag_is_raised(self) -> None:
        """赤い鍵の旗が立っていなければ偽、立てたあとは真、下ろしたあとはまた偽。"""
        condition = FlagIsRaisedCondition(flag=_RED_KEY, failure_text=NoText())
        a_world = world()
        assert not condition.holds(a_world.facts(), _BY_ALICE)

        a_world.flags.raise_flag(_RED_KEY, _DAWN)
        assert condition.holds(a_world.facts(), _BY_ALICE)

        a_world.flags.lower_flag(_RED_KEY, _DAWN)
        assert not condition.holds(a_world.facts(), _BY_ALICE)

    def test_flag_declared_raised_holds_from_the_start(self) -> None:
        """初めから立っていると宣言した旗の条件は、立て下ろしをしていない世界で真。"""
        assert FlagIsRaisedCondition(flag=_GREEN_KEY, failure_text=NoText()).holds(world().facts(), _BY_ALICE)

    def test_failure_carries_its_own_text_about_actor(self) -> None:
        """旗が立っていないとき、自分の位置と、failure_text の {actor} に行う人を当てた文を返す。"""
        condition = FlagIsRaisedCondition(flag=_RED_KEY, failure_text=text("{actor}はまだ鍵を持たない"))

        assert condition.failure_reason(world().facts(), _BY_ALICE) == FailureReason(
            failed_part=ConditionPath.root(), text=text("{actor}はまだ鍵を持たない").about({"actor": ALICE})
        )

    def test_requirements_wait_for_the_flag(self) -> None:
        """requirements() は、主語も偶然も引数も要らず、見ている旗だけを waits_for_flags に持つ。"""
        requirements = FlagIsRaisedCondition(flag=_RED_KEY, failure_text=NoText()).requirements()

        assert requirements == Requirements(
            subjects=frozenset(),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset({_RED_KEY}),
        )

    def test_requirements_include_placeholder_of_failure_text(self) -> None:
        """failure_text に {target} があれば、旗の条件でも requirements() は TARGET を要る。"""
        condition = FlagIsRaisedCondition(flag=_RED_KEY, failure_text=text("{target}が鍵を隠している"))

        assert condition.requirements().subjects == frozenset({SubjectKind.TARGET})


class TestFlagsRaisedAtLeastCondition:
    """FlagsRaisedAtLeastCondition が、挙げた旗のうち今立っている数が count 以上かで真偽を決めることを保証する。"""

    def test_holds_when_raised_flags_reach_the_count(self) -> None:
        """3 つの鍵の旗のうち 2 つ以上の条件は、立っているのが緑の 1 つなら偽、赤も立てて 2 つなら真。"""
        condition = FlagsRaisedAtLeastCondition(
            flags=(_RED_KEY, _BLUE_KEY, _GREEN_KEY), count=Count(2), failure_text=NoText()
        )

        assert not condition.holds(world().facts(), _BY_ALICE)
        assert condition.holds(_with_raised(_RED_KEY).facts(), _BY_ALICE)

    def test_flags_outside_the_list_are_not_counted(self) -> None:
        """挙げていない旗がいくつ立っていても数えない。赤と青だけを挙げた 1 つ以上の条件は、緑だけが立っていれば偽。"""
        condition = FlagsRaisedAtLeastCondition(flags=(_RED_KEY, _BLUE_KEY), count=Count(1), failure_text=NoText())

        assert not condition.holds(world().facts(), _BY_ALICE)

    def test_zero_count_always_holds(self) -> None:
        """count が 0 なら、旗が 1 つも立っていなくても真。"""
        condition = FlagsRaisedAtLeastCondition(flags=(_RED_KEY,), count=Count(0), failure_text=NoText())

        assert condition.holds(world().facts(), _BY_ALICE)

    def test_failure_carries_its_own_text(self) -> None:
        """数が足りないとき、自分の位置と自分の failure_text の文を返す。"""
        condition = FlagsRaisedAtLeastCondition(
            flags=(_RED_KEY, _BLUE_KEY), count=Count(2), failure_text=text("鍵がまだ揃わない")
        )

        assert condition.failure_reason(_with_raised(_RED_KEY).facts(), _BY_ALICE) == FailureReason(
            failed_part=ConditionPath.root(), text=text("鍵がまだ揃わない").about({})
        )

    def test_requirements_wait_for_every_listed_flag(self) -> None:
        """requirements() は、挙げた旗のすべてを waits_for_flags に持ち、ほかは何も要らない。"""
        requirements = FlagsRaisedAtLeastCondition(
            flags=(_RED_KEY, _BLUE_KEY), count=Count(1), failure_text=NoText()
        ).requirements()

        assert requirements == Requirements(
            subjects=frozenset(),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset({_RED_KEY, _BLUE_KEY}),
        )
