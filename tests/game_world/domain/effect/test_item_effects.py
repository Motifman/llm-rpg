from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, SubjectKind, Target, ThisItem
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    FlagStateKind,
    FlagValue,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    NotALightSource,
)
from ai_rpg_world.game_world.domain.effect.item_effects import (
    Anywhere,
    GiveItemEffect,
    InHands,
    InPack,
    ItemByArgument,
    MoveItemEffect,
    RandomItemOf,
    SetItemValueEffect,
    TakeItemEffect,
)
from ai_rpg_world.game_world.domain.exception.effect_exception import ArgumentIsNotAnItemException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    InventoryFullException,
    NotEnoughItemsOfSpecException,
)
from ai_rpg_world.game_world.domain.exception.person_inventory_exception import (
    ItemNotHeldException,
    ItemNotPackedException,
    PackIsEmptyException,
)
from ai_rpg_world.game_world.domain.objects_and_items import Item, ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    HandsNeeded,
    ItemSpecId,
    StateKeyId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from tests.game_world.domain.effect._builders import ALICE, BOB, WORLD, inventory, item_spec
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_APPLE = item_spec("apple")
_ROPE = item_spec("rope")
_KNIFE = item_spec("knife")
_LANTERN = item_spec("lantern")
_THE_ITEM = ArgumentName("the_item")


def _world(
    *items: tuple[ItemInstanceId, ItemSpecDeclaration], capacity: int = 10, fractions: tuple[float, ...] = ()
) -> WorldInMemory:
    alice = inventory(ALICE, capacity)
    for item_id, spec in items:
        alice.receive(item_id, spec.item_spec_id)
    return WorldInMemory(
        world=WORLD,
        people=(ALICE, BOB),
        inventories=(alice, inventory(BOB)),
        items=tuple(Item.come_into_world(item_id, spec, WorldTick(0)) for item_id, spec in items),
        fractions=fractions,
    )


def _held(world: WorldInMemory, item: ItemInstanceId) -> None:
    world.inventories[ALICE].hold(item, HandsNeeded(1))


def _bob_acts(**arguments: TextArgumentValue | ItemInstanceId) -> ActionAttemptForTests:
    return ActionAttemptForTests(
        actor_id=BOB, target=ALICE, arguments={ArgumentName(name): value for name, value in arguments.items()}
    )


_APPLE_1 = ItemInstanceId("apple#1")
_APPLE_2 = ItemInstanceId("apple#2")
_APPLE_3 = ItemInstanceId("apple#3")
_ROPE_1 = ItemInstanceId("rope#1")
_KNIFE_1 = ItemInstanceId("knife#1")
_LANTERN_1 = ItemInstanceId("lantern#1")


class TestGiveItemEffect:
    """GiveItemEffect が、新しい品物を数だけ世界に生み、その人の荷に入れることを保証する。"""

    def test_brings_new_items_into_world_and_packs_them(self) -> None:
        """Alice にりんごを 2 つ与えると、世界に新しいりんごが 2 つ増え、どちらも Alice の荷に入る。"""
        world = _world()

        GiveItemEffect(Actor(), _APPLE, Count(2)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
        )

        given = world.inventories[ALICE].packed_items()
        assert len(given) == 2
        assert all(world.items[item].spec_id == _APPLE.item_spec_id for item in given)
        assert world.inventories[ALICE].count_of(_APPLE.item_spec_id) == Count(2)

    def test_full_pack_refusal_comes_out_as_domain_exception(self) -> None:
        """荷が満杯の Alice に与えると、PersonInventory が InventoryFullException で断り、効果はそのまま外へ出す。"""
        world = _world((_ROPE_1, _ROPE), capacity=1)

        with pytest.raises(InventoryFullException):
            GiveItemEffect(Actor(), _APPLE, Count(1)).apply(
                world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
            )


class TestTakeItemEffect:
    """TakeItemEffect が、その種類の品物を荷から先に取り、世界から消すことを保証する。"""

    def test_takes_items_from_pack_first_and_removes_them_from_world(self) -> None:
        """りんごを 1 つ手に、2 つ荷に持つ Alice から 2 つ取ると、荷の 2 つが世界から消え、手の 1 つが残る。"""
        world = _world((_APPLE_1, _APPLE), (_APPLE_2, _APPLE), (_APPLE_3, _APPLE))
        _held(world, _APPLE_1)

        TakeItemEffect(Actor(), _APPLE, Count(2)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
        )

        assert world.inventories[ALICE].items() == (_APPLE_1,)
        assert set(world.items) == {_APPLE_1}

    def test_takes_nothing_when_too_few(self) -> None:
        """りんごを 1 つしか持たない Alice から 2 つ取ろうとすると、NotEnoughItemsOfSpecException で断り、1 つも取らない。"""
        world = _world((_APPLE_1, _APPLE))

        with pytest.raises(NotEnoughItemsOfSpecException):
            TakeItemEffect(Actor(), _APPLE, Count(2)).apply(
                world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE)
            )

        assert world.inventories[ALICE].items() == (_APPLE_1,)
        assert set(world.items) == {_APPLE_1}


class TestMoveItemEffectByArgument:
    """MoveItemEffect に ItemByArgument を渡すと、引数で指した同じ品物を、指した場所から受け取る人の荷へ移すことを保証する。"""

    def test_moves_held_item_from_hands(self) -> None:
        """Bob が Alice の手のカンテラを InHands で奪うと、同じカンテラが Bob の荷に入り、Alice の持ち物から消える。"""
        world = _world((_LANTERN_1, _LANTERN))
        _held(world, _LANTERN_1)

        MoveItemEffect(Target(), Actor(), ItemByArgument(_THE_ITEM, InHands())).apply(
            world.facts(), world.aggregates(), _bob_acts(the_item=_LANTERN_1)
        )

        assert world.inventories[ALICE].items() == ()
        assert world.inventories[BOB].packed_items() == (_LANTERN_1,)
        assert world.inventories[BOB].count_of(_LANTERN.item_spec_id) == Count(1)

    def test_in_hands_refuses_packed_item(self) -> None:
        """荷にある縄を InHands で指すと、ItemNotHeldException で断り、どちらの持ち物も変わらない。"""
        world = _world((_ROPE_1, _ROPE))

        with pytest.raises(ItemNotHeldException):
            MoveItemEffect(Target(), Actor(), ItemByArgument(_THE_ITEM, InHands())).apply(
                world.facts(), world.aggregates(), _bob_acts(the_item=_ROPE_1)
            )

        assert world.inventories[ALICE].items() == (_ROPE_1,)
        assert world.inventories[BOB].items() == ()

    def test_in_pack_refuses_held_item(self) -> None:
        """手にあるカンテラを InPack で指すと、ItemNotPackedException で断る。"""
        world = _world((_LANTERN_1, _LANTERN))
        _held(world, _LANTERN_1)

        with pytest.raises(ItemNotPackedException):
            MoveItemEffect(Target(), Actor(), ItemByArgument(_THE_ITEM, InPack())).apply(
                world.facts(), world.aggregates(), _bob_acts(the_item=_LANTERN_1)
            )

    @pytest.mark.parametrize("held", [True, False])
    def test_anywhere_moves_item_from_hands_or_pack(self, held: bool) -> None:
        """Anywhere で指すと、縄が手にあっても荷にあっても Bob の荷へ移す。"""
        world = _world((_ROPE_1, _ROPE))
        if held:
            _held(world, _ROPE_1)

        MoveItemEffect(Target(), Actor(), ItemByArgument(_THE_ITEM, Anywhere())).apply(
            world.facts(), world.aggregates(), _bob_acts(the_item=_ROPE_1)
        )

        assert world.inventories[BOB].packed_items() == (_ROPE_1,)

    def test_text_argument_is_refused(self) -> None:
        """品物を指すはずの引数に文が入っていると、ArgumentIsNotAnItemException を投げ、何も移さない。"""
        world = _world((_ROPE_1, _ROPE))

        with pytest.raises(ArgumentIsNotAnItemException):
            MoveItemEffect(Target(), Actor(), ItemByArgument(_THE_ITEM, Anywhere())).apply(
                world.facts(), world.aggregates(), _bob_acts(the_item=TextArgumentValue("縄"))
            )

        assert world.inventories[ALICE].items() == (_ROPE_1,)

    def test_requires_both_subjects_and_the_argument(self) -> None:
        """要るものは、手放す人と受け取る人の主語と、読む引数の名前。"""
        effect = MoveItemEffect(Target(), Actor(), ItemByArgument(_THE_ITEM, InHands()))

        assert effect.requirements() == Requirements(
            subjects=frozenset({SubjectKind.TARGET, SubjectKind.ACTOR}),
            uses_chance=False,
            uses_action_arguments=frozenset({_THE_ITEM}),
            waits_for_flags=frozenset(),
        )


class TestMoveItemEffectRandomItemOf:
    """MoveItemEffect に RandomItemOf を渡すと、手放す人の荷から偶然で 1 つ選んで移すことを保証する。"""

    def test_moves_packed_item_chosen_by_chance(self) -> None:
        """荷に縄・ナイフを入れた順に持つ Alice から、0.6 を引くとナイフが Bob の荷へ移る。"""
        world = _world((_ROPE_1, _ROPE), (_KNIFE_1, _KNIFE), fractions=(0.6,))

        MoveItemEffect(Target(), Actor(), RandomItemOf()).apply(world.facts(), world.aggregates(), _bob_acts())

        assert world.inventories[ALICE].items() == (_ROPE_1,)
        assert world.inventories[BOB].packed_items() == (_KNIFE_1,)

    def test_empty_pack_is_refused_by_inventory(self) -> None:
        """Alice の荷が空なら (手にカンテラを持っていても)、PersonInventory が PackIsEmptyException で断る。"""
        world = _world((_LANTERN_1, _LANTERN), fractions=(0.0,))
        _held(world, _LANTERN_1)

        with pytest.raises(PackIsEmptyException):
            MoveItemEffect(Target(), Actor(), RandomItemOf()).apply(world.facts(), world.aggregates(), _bob_acts())

        assert world.inventories[ALICE].items() == (_LANTERN_1,)

    def test_requires_both_subjects_and_chance(self) -> None:
        """要るものは、手放す人と受け取る人の主語と、偶然。"""
        assert MoveItemEffect(Target(), Actor(), RandomItemOf()).requirements() == Requirements(
            subjects=frozenset({SubjectKind.TARGET, SubjectKind.ACTOR}),
            uses_chance=True,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
        )


class TestSetItemValueEffect:
    """SetItemValueEffect が、きっかけの品物の状態の鍵に値を置くことを保証する。"""

    def test_sets_value_on_item_of_trigger(self) -> None:
        """Alice が使ったカンテラの「灯っている」を真にすると、そのカンテラの値が真になる。"""
        lit = ItemStateKeyDeclaration(
            item_spec_id=ItemSpecId("lantern"), key=StateKeyId("lit"), kind=FlagStateKind(), initial=FlagValue(False)
        )
        lantern = ItemSpecDeclaration(
            item_spec_id=ItemSpecId("lantern"),
            name=DisplayName("カンテラ"),
            description=DescriptionText("古いカンテラ"),
            state_keys=(lit,),
            lights_up=NotALightSource(),
        )
        world = _world((_LANTERN_1, lantern))

        SetItemValueEffect(ThisItem(), lit, FlagValue(True)).apply(
            world.facts(), world.aggregates(), ActionAttemptForTests(actor_id=ALICE, item=_LANTERN_1)
        )

        assert world.items[_LANTERN_1].value_of(lit) == FlagValue(True)
