from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.argument_condition import ArgumentEqualsCondition
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.item_conditions import ItemAgeAtLeastCondition, ItemValueIsCondition
from ai_rpg_world.game_world.domain.condition.subject import ThisItem
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    FlagStateKind,
    FlagValue,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    NotALightSource,
)
from ai_rpg_world.game_world.domain.exception.trigger_exception import ArgumentNotInTriggerException
from ai_rpg_world.game_world.domain.objects_and_items import Item
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    ItemSpecId,
    StateKeyId,
    Ticks,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.condition._builders import ALICE, WORLD
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_LIT = ItemStateKeyDeclaration(
    item_spec_id=ItemSpecId("torch"), key=StateKeyId("lit"), kind=FlagStateKind(), initial=FlagValue(False)
)
_TORCH = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("torch"),
    name=DisplayName("松明"),
    description=DescriptionText("油を染みこませた松明"),
    state_keys=(_LIT,),
    lights_up=NotALightSource(),
    hands_needed=HandsNeeded(1),
)
_PASSWORD = ArgumentName("password")


def _world_with_torch_from(tick: int) -> tuple[WorldInMemory, ItemInstanceId]:
    torch = Item.come_into_world(ItemInstanceId("torch-1"), _TORCH, WorldTick(tick))
    a_world = WorldInMemory(world=WORLD, items=(torch,))
    for _ in range(3):
        a_world.clock().advance(a_world.day_night)
    return a_world, torch.item_id


class TestItemConditions:
    """ItemAgeAtLeastCondition と ItemValueIsCondition が、きっかけの品物を facts.item() で読むことを保証する。"""

    def test_item_age_at_least(self) -> None:
        """tick 1 に世界に出た松明は tick 3 に 2 tick 経っているので、2 tick 以上は真、3 tick 以上は偽。"""
        a_world, torch = _world_with_torch_from(1)
        using_torch = ActionAttemptForTests(actor_id=ALICE, item=torch)

        assert ItemAgeAtLeastCondition(item=ThisItem(), ticks=Ticks(2), failure_text=NoText()).holds(
            a_world.facts(), using_torch
        )
        assert not ItemAgeAtLeastCondition(item=ThisItem(), ticks=Ticks(3), failure_text=NoText()).holds(
            a_world.facts(), using_torch
        )

    def test_item_value_is(self) -> None:
        """灯していない松明は、灯していない条件で真、灯している条件で偽。"""
        a_world, torch = _world_with_torch_from(0)
        using_torch = ActionAttemptForTests(actor_id=ALICE, item=torch)

        assert ItemValueIsCondition(item=ThisItem(), key=_LIT, value=FlagValue(False), failure_text=NoText()).holds(
            a_world.facts(), using_torch
        )
        assert not ItemValueIsCondition(item=ThisItem(), key=_LIT, value=FlagValue(True), failure_text=NoText()).holds(
            a_world.facts(), using_torch
        )


class TestArgumentEquals:
    """ArgumentEqualsCondition が、きっかけの文の引数と比べることを保証する。"""

    def test_same_text_holds(self) -> None:
        """合言葉に「ひらけ」と書いた行為は、「ひらけ」と等しい条件で真、「とじろ」で偽。"""
        attempt = ActionAttemptForTests(actor_id=ALICE, arguments={_PASSWORD: TextArgumentValue("ひらけ")})
        facts = WorldInMemory(world=WORLD).facts()

        assert ArgumentEqualsCondition(
            argument=_PASSWORD, expected=TextArgumentValue("ひらけ"), failure_text=NoText()
        ).holds(facts, attempt)
        assert not ArgumentEqualsCondition(
            argument=_PASSWORD, expected=TextArgumentValue("とじろ"), failure_text=NoText()
        ).holds(facts, attempt)

    def test_item_argument_never_equals_text(self) -> None:
        """引数が品物なら、どの文とも等しくなく偽。"""
        attempt = ActionAttemptForTests(actor_id=ALICE, arguments={_PASSWORD: ItemInstanceId("torch-1")})

        assert not ArgumentEqualsCondition(
            argument=_PASSWORD, expected=TextArgumentValue("torch-1"), failure_text=NoText()
        ).holds(WorldInMemory(world=WORLD).facts(), attempt)

    def test_requires_the_argument_name(self) -> None:
        """requirements() の uses_action_arguments に、読む引数の名前が入る。"""
        condition = ArgumentEqualsCondition(
            argument=_PASSWORD, expected=TextArgumentValue("ひらけ"), failure_text=NoText()
        )

        assert condition.requirements().uses_action_arguments == frozenset({_PASSWORD})

    def test_trigger_without_arguments_fails_loudly(self) -> None:
        """引数を持たない出来事のきっかけで見ると、ArgumentNotInTriggerException を投げる。"""
        condition = ArgumentEqualsCondition(
            argument=_PASSWORD, expected=TextArgumentValue("ひらけ"), failure_text=NoText()
        )

        with pytest.raises(ArgumentNotInTriggerException):
            condition.holds(WorldInMemory(world=WORLD).facts(), HappeningFired(HappeningForTests(HappeningId("dawn"))))
