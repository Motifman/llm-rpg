from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.object_state_conditions import (
    ObjectCountAtLeastCondition,
    ObjectCountGreaterThanCondition,
    ObjectStockAtLeastCondition,
    ObjectValueIsCondition,
)
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
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
from ai_rpg_world.game_world.domain.exception.condition_exception import StateValueOfAnotherKindException
from ai_rpg_world.game_world.domain.objects_and_items import ObjectState
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
from tests.game_world.support.world_in_memory import WorldInMemory

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
    return WorldInMemory(
        world=WORLD,
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

    def test_count_of_a_key_that_is_not_a_count_fails_loudly(self) -> None:
        """数でない値 (蓋の開け閉め) を数として見ると、StateValueOfAnotherKindException を投げる。"""
        with pytest.raises(StateValueOfAnotherKindException):
            ObjectCountAtLeastCondition(key=_LID, count=Count(1), failure_text=NoText()).holds(_facts(), _BY_ALICE)


class TestObjectStockAtLeast:
    """ObjectStockAtLeastCondition が在庫の量を比べることを保証する。"""

    def test_stock_at_least(self) -> None:
        """池の魚が 2 匹なら、2 匹以上は真、3 匹以上は偽。"""
        facts = _facts()

        assert ObjectStockAtLeastCondition(key=_FISH, amount=Count(2), failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not ObjectStockAtLeastCondition(key=_FISH, amount=Count(3), failure_text=NoText()).holds(
            facts, _BY_ALICE
        )

    def test_stock_of_a_key_that_is_not_a_stock_fails_loudly(self) -> None:
        """在庫でない値 (硬貨の数) を在庫として見ると、StateValueOfAnotherKindException を投げる。"""
        with pytest.raises(StateValueOfAnotherKindException):
            ObjectStockAtLeastCondition(key=_COINS, amount=Count(1), failure_text=NoText()).holds(_facts(), _BY_ALICE)
