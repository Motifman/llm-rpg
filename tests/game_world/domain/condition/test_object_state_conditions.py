from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition, AnyOfCondition, NotCondition
from ai_rpg_world.game_world.domain.condition.object_state_conditions import (
    ObjectCountAtLeastCondition,
    ObjectCountGreaterThanCondition,
    ObjectStockAtLeastCondition,
    ObjectValueIsCondition,
)
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    CountStateKind,
    CountValue,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
    StockStateKind,
    StockValue,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_kind import NoRefill, StateKind
from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import (
    StateKeyOfAnotherKindException,
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.objects_and_items import ObjectState
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    ObjectId,
    SpotId,
    StateKeyId,
    WorldTick,
)
from tests.game_world.domain.condition._builders import ALICE, WORLD
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_design_for_tests import spot
from tests.game_world.support.world_in_memory import world_in_memory

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)
_OPEN = ChoiceName("open")
_SHUT = ChoiceName("shut")


def _key(object_id: str, key: str, kind: StateKind, initial: StateValue) -> ObjectStateKeyDeclaration:
    return ObjectStateKeyDeclaration(object_id=ObjectId(object_id), key=StateKeyId(key), kind=kind, initial=initial)


def _object(object_id: str, *keys: ObjectStateKeyDeclaration) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=ObjectId(object_id),
        spot_id=SpotId("square"),
        name=DisplayName(object_id),
        description=DescriptionText(f"{object_id}がある"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=False),
        state_keys=keys,
    )


_LID = _key("chest", "lid", ChoiceStateKind(choices=(_OPEN, _SHUT)), ChoiceValue(_SHUT))
_COINS = _key("chest", "coins", CountStateKind(), CountValue(Count(3)))
_CHEST = _object("chest", _LID, _COINS)
_PEBBLES = _key("jar", "pebbles", CountStateKind(), CountValue(Count(5)))
_JAR = _object("jar", _PEBBLES)
_FISH = _key("pond", "fish", StockStateKind(capacity=Count(4), refills_every=NoRefill()), StockValue(Count(2)))
_POND = _object("pond", _FISH)


def _facts() -> WorldFacts:
    return world_in_memory(
        world=WORLD,
        spots=(spot("square"),),
        objects=(_CHEST, _JAR, _POND),
        object_states=tuple(
            ObjectState.from_declaration(declaration, WorldTick(0)) for declaration in (_CHEST, _JAR, _POND)
        ),
    ).facts()


class TestObjectValueIs:
    """ObjectValueIsCondition が facts.object_state() の今の値と比べることを保証する。"""

    def test_same_value_holds(self) -> None:
        """閉じた箱の蓋が閉じている条件は真、開いている条件は偽。"""
        facts = _facts()

        assert ObjectValueIsCondition(key=_LID, value=ChoiceValue(_SHUT), failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not ObjectValueIsCondition(key=_LID, value=ChoiceValue(_OPEN), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )

    def test_value_that_does_not_fit_the_key_is_refused(self) -> None:
        """蓋の開け閉めの鍵を、選択肢に無い値 (割れた) と比べる ObjectValueIsCondition は StateValueMismatchesKindException を投げる。"""
        with pytest.raises(StateValueMismatchesKindException):
            ObjectValueIsCondition(key=_LID, value=ChoiceValue(ChoiceName("broken")), failure_text=NoText())


class TestObjectCounts:
    """ObjectCountAtLeastCondition と ObjectCountGreaterThanCondition が数の値を比べることを保証する。"""

    def test_count_at_least(self) -> None:
        """箱の硬貨が 3 枚なら、3 枚以上は真、4 枚以上は偽。"""
        facts = _facts()

        assert ObjectCountAtLeastCondition(key=_COINS, count=Count(3), failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not ObjectCountAtLeastCondition(key=_COINS, count=Count(4), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )

    def test_count_greater_than_another_object(self) -> None:
        """壺の小石 5 は箱の硬貨 3 より多いので真、逆は偽。"""
        facts = _facts()

        assert ObjectCountGreaterThanCondition(key=_PEBBLES, other=_COINS, failure_text=NoText()).holds(
            facts, _BY_ALICE
        )
        assert not ObjectCountGreaterThanCondition(key=_COINS, other=_PEBBLES, failure_text=NoText()).holds(
            facts, _BY_ALICE
        )

    def test_count_at_least_of_a_key_that_is_not_a_count_is_refused(self) -> None:
        """数でない鍵 (蓋の開け閉め) を数として見る ObjectCountAtLeastCondition は StateKeyOfAnotherKindException を投げる。"""
        with pytest.raises(StateKeyOfAnotherKindException):
            ObjectCountAtLeastCondition(key=_LID, count=Count(1), failure_text=NoText())

    @pytest.mark.parametrize(
        ("key", "other"), [pytest.param(_LID, _COINS, id="key"), pytest.param(_COINS, _FISH, id="other")]
    )
    def test_count_greater_than_with_a_key_that_is_not_a_count_is_refused(
        self, key: ObjectStateKeyDeclaration, other: ObjectStateKeyDeclaration
    ) -> None:
        """比べる 2 つの鍵のどちらかが数でない (蓋の開け閉め・池の魚の在庫) と、StateKeyOfAnotherKindException を投げる。"""
        with pytest.raises(StateKeyOfAnotherKindException):
            ObjectCountGreaterThanCondition(key=key, other=other, failure_text=NoText())


class TestObjectStockAtLeast:
    """ObjectStockAtLeastCondition が在庫の量を比べることを保証する。"""

    def test_stock_at_least(self) -> None:
        """池の魚が 2 匹なら、2 匹以上は真、3 匹以上は偽。"""
        facts = _facts()

        assert ObjectStockAtLeastCondition(key=_FISH, amount=Count(2), failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not ObjectStockAtLeastCondition(key=_FISH, amount=Count(3), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )

    def test_stock_of_a_key_that_is_not_a_stock_is_refused(self) -> None:
        """在庫でない鍵 (硬貨の数) を在庫として見る ObjectStockAtLeastCondition は StateKeyOfAnotherKindException を投げる。"""
        with pytest.raises(StateKeyOfAnotherKindException):
            ObjectStockAtLeastCondition(key=_COINS, amount=Count(1), failure_text=NoText())


class TestFailureAboutObjectState:
    """物の状態・数を見る条件が偽になると、その理由が「物の状態で断られた」と分かることを保証する。場面の物の行に「いまできない」を出すかを、これで決める。"""

    @pytest.mark.parametrize(
        "condition",
        [
            ObjectValueIsCondition(key=_LID, value=ChoiceValue(_OPEN), failure_text=NoText()),
            ObjectCountAtLeastCondition(key=_COINS, count=Count(4), failure_text=NoText()),
            ObjectCountGreaterThanCondition(key=_COINS, other=_PEBBLES, failure_text=NoText()),
            ObjectStockAtLeastCondition(key=_FISH, amount=Count(3), failure_text=NoText()),
        ],
    )
    def test_failure_of_object_state_condition_is_about_object_state(self, condition: object) -> None:
        """蓋・硬貨・在庫のどの条件でも、偽のときの理由は about_object_state を持つ。"""
        reason = condition.failure_reason(_facts(), _BY_ALICE)  # type: ignore[attr-defined]

        assert isinstance(reason, FailureReason) and reason.about_object_state

    def test_all_of_keeps_it_from_the_failed_child(self) -> None:
        """AllOf の中で在庫の条件が偽になると、AllOf の理由も about_object_state を持つ。"""
        condition = AllOfCondition(children=(_lid_is_shut(), _three_fish()), failure_text=NoText())

        reason = condition.failure_reason(_facts(), _BY_ALICE)

        assert isinstance(reason, FailureReason) and reason.about_object_state

    def test_all_of_keeps_it_when_the_failed_child_explains_itself(self) -> None:
        """AllOf の中で、自分の断りの文を持つ在庫の条件が偽になると、その文とともに about_object_state を引き継ぐ。"""
        fish = ObjectStockAtLeastCondition(
            key=_FISH, amount=Count(3), failure_text=TextWithUnassignedPeople("魚が足りない。")
        )
        condition = AllOfCondition(children=(_lid_is_shut(), fish), failure_text=NoText())

        reason = condition.failure_reason(_facts(), _BY_ALICE)

        assert isinstance(reason, FailureReason) and reason.about_object_state

    def test_any_of_has_it_when_some_failed_child_has_it(self) -> None:
        """AnyOf の子がすべて偽で、そのうち 1 つが在庫の条件なら、理由は about_object_state を持つ。"""
        never = TickAtLeastCondition(tick=WorldTick(99), failure_text=NoText())
        condition = AnyOfCondition(children=(never, _three_fish()), failure_text=TextWithUnassignedPeople("駄目"))

        reason = condition.failure_reason(_facts(), _BY_ALICE)

        assert isinstance(reason, FailureReason) and reason.about_object_state

    def test_negated_object_state_condition_is_not_about_object_state(self) -> None:
        """「蓋が閉じていない」のように物の状態の条件を not で包むと、偽のときの理由は about_object_state を持たない。古い run に否定の形の状態の条件は無く、出すものを広げないため。"""
        reason = NotCondition(_lid_is_shut(), NoText()).failure_reason(_facts(), _BY_ALICE)

        assert isinstance(reason, FailureReason) and not reason.about_object_state

    def test_any_of_without_object_state_does_not_have_it(self) -> None:
        """AnyOf の子がすべて偽で、どれも物の状態を見ない条件なら、理由は about_object_state を持たない。"""
        never = TickAtLeastCondition(tick=WorldTick(99), failure_text=NoText())
        condition = AnyOfCondition(children=(never, never), failure_text=TextWithUnassignedPeople("駄目"))

        reason = condition.failure_reason(_facts(), _BY_ALICE)

        assert isinstance(reason, FailureReason) and not reason.about_object_state

    def test_failure_of_other_condition_is_not_about_object_state(self) -> None:
        """物の状態を見ない条件 (時刻) が偽のときの理由は、about_object_state を持たない。"""
        never = TickAtLeastCondition(tick=WorldTick(99), failure_text=NoText())

        reason = AllOfCondition(children=(_lid_is_shut(), never), failure_text=NoText()).failure_reason(
            _facts(), _BY_ALICE
        )

        assert isinstance(reason, FailureReason) and not reason.about_object_state


def _lid_is_shut() -> ObjectValueIsCondition:
    return ObjectValueIsCondition(key=_LID, value=ChoiceValue(_SHUT), failure_text=NoText())


def _three_fish() -> ObjectStockAtLeastCondition:
    return ObjectStockAtLeastCondition(key=_FISH, amount=Count(3), failure_text=NoText())
