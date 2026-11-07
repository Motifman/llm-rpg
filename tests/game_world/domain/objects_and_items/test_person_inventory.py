from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import InsufficientGoldException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    InventoryFullException,
    ItemAlreadyCarriedException,
    ItemNotCarriedException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    GoldEarnedEvent,
    GoldPaidEvent,
    ItemGivenUpEvent,
    ItemHeldEvent,
    ItemInstanceId,
    ItemPutAwayEvent,
    ItemReceivedEvent,
    PersonInventory,
)
from ai_rpg_world.game_world.domain.value_object import Capacity, Gold, HandsNeeded, PersonId

_ALICE = PersonId("alice")
_LANTERN = ItemInstanceId("lantern#1")
_KNIFE = ItemInstanceId("knife#1")
_ROPE = ItemInstanceId("rope#1")
_PICKAXE = ItemInstanceId("pickaxe#1")
_ONE_HAND = HandsNeeded(1)
_TWO_HANDS = HandsNeeded(2)


def _inventory(*items: ItemInstanceId, capacity: int = 10) -> PersonInventory:
    inventory = PersonInventory(_ALICE, Capacity(capacity))
    for item in items:
        inventory.receive(item)
    inventory.clear_events()
    return inventory


class TestPersonInventoryReceiveAndGiveUp:
    """PersonInventory の receive / give_up が、品物を荷に入れ、手の物でも荷の物でも手放させることを保証する。"""

    def test_starts_empty_for_its_person(self) -> None:
        """作った直後は自分の人の ID を持ち、品物も金も無く、満杯でもない。"""
        inventory = PersonInventory(_ALICE, Capacity(2))

        assert inventory.person_id == _ALICE
        assert inventory.items() == ()
        assert inventory.available_gold() == Gold(0)
        assert not inventory.is_full()

    def test_receive_puts_item_in_pack_and_records_event(self) -> None:
        """receive した品物は荷に入り、手には無く、持ち主と品物を持つ ItemReceivedEvent がたまる。"""
        inventory = _inventory()

        inventory.receive(_LANTERN)

        assert inventory.packed_items() == (_LANTERN,)
        assert inventory.held_items() == ()
        [event] = inventory.get_events()
        assert isinstance(event, ItemReceivedEvent)
        assert (event.person, event.item) == (_ALICE, _LANTERN)

    def test_receiving_an_item_already_carried_is_refused(self) -> None:
        """もう持っている品物を receive すると ItemAlreadyCarriedException を投げ、イベントはたまらない。"""
        inventory = _inventory(_LANTERN)

        with pytest.raises(ItemAlreadyCarriedException):
            inventory.receive(_LANTERN)

        assert inventory.items() == (_LANTERN,)
        assert inventory.get_events() == []

    def test_is_full_counts_held_items_too(self) -> None:
        """手に持った物も数に入れ、品物の数が上限に達すると is_full が True を返す。"""
        inventory = _inventory(_LANTERN, capacity=2)
        inventory.hold(_LANTERN, _ONE_HAND)
        assert not inventory.is_full()

        inventory.receive(_KNIFE)

        assert inventory.is_full()

    def test_receiving_when_full_is_refused(self) -> None:
        """満杯のときに receive すると InventoryFullException を投げ、品物もイベントも増えない。"""
        inventory = _inventory(_LANTERN, _KNIFE, capacity=2)

        with pytest.raises(InventoryFullException):
            inventory.receive(_ROPE)

        assert inventory.items() == (_LANTERN, _KNIFE)
        assert inventory.get_events() == []

    def test_give_up_removes_packed_item(self) -> None:
        """荷の物を give_up すると持ち物から無くなり、手に持っていなかったことを示す ItemGivenUpEvent がたまる。"""
        inventory = _inventory(_LANTERN, _KNIFE)

        inventory.give_up(_LANTERN)

        assert inventory.items() == (_KNIFE,)
        [event] = inventory.get_events()
        assert isinstance(event, ItemGivenUpEvent)
        assert (event.person, event.item, event.was_held) == (_ALICE, _LANTERN, False)

    def test_give_up_removes_held_item(self) -> None:
        """手の物を give_up すると手からも持ち物からも無くなり、手に持っていたことを示す ItemGivenUpEvent がたまる。"""
        inventory = _inventory(_LANTERN)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.clear_events()

        inventory.give_up(_LANTERN)

        assert inventory.items() == ()
        assert inventory.held_items() == ()
        [event] = inventory.get_events()
        assert isinstance(event, ItemGivenUpEvent)
        assert event.was_held

    def test_giving_up_an_item_not_carried_is_refused(self) -> None:
        """持っていない品物を give_up すると ItemNotCarriedException を投げ、イベントはたまらない。"""
        inventory = _inventory(_LANTERN)

        with pytest.raises(ItemNotCarriedException):
            inventory.give_up(_KNIFE)

        assert inventory.get_events() == []


class TestPersonInventoryHoldAndPutAway:
    """PersonInventory の hold / put_away が、2 本の手と荷のあいだで品物を動かすことを保証する。"""

    def test_hold_moves_item_from_pack_to_hands(self) -> None:
        """荷の物を hold すると手に移って荷から無くなり、持ち主と品物を持つ ItemHeldEvent がたまる。"""
        inventory = _inventory(_LANTERN, _KNIFE)

        inventory.hold(_LANTERN, _ONE_HAND)

        assert inventory.held_items() == (_LANTERN,)
        assert inventory.packed_items() == (_KNIFE,)
        [event] = inventory.get_events()
        assert isinstance(event, ItemHeldEvent)
        assert (event.person, event.item) == (_ALICE, _LANTERN)

    def test_held_and_packed_items_are_separate_and_items_has_both(self) -> None:
        """held_items は手の物だけ、packed_items は荷の物だけを返し、items は両方を含む。"""
        inventory = _inventory(_LANTERN, _KNIFE, _ROPE)

        inventory.hold(_KNIFE, _ONE_HAND)

        assert inventory.held_items() == (_KNIFE,)
        assert inventory.packed_items() == (_LANTERN, _ROPE)
        assert set(inventory.items()) == {_LANTERN, _KNIFE, _ROPE}

    def test_two_one_handed_items_fit_in_two_hands(self) -> None:
        """片手の物を 2 つ hold すると、どちらも手に残る。"""
        inventory = _inventory(_LANTERN, _KNIFE)

        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.hold(_KNIFE, _ONE_HAND)

        assert inventory.held_items() == (_LANTERN, _KNIFE)

    def test_holding_two_handed_item_puts_away_everything_in_hands(self) -> None:
        """両手が要る品物を持つと、今手に持っている物をすべて荷にしまい、ItemPutAwayEvent のあとに ItemHeldEvent がたまる。"""
        inventory = _inventory(_LANTERN, _KNIFE, _PICKAXE)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.hold(_KNIFE, _ONE_HAND)
        inventory.clear_events()

        inventory.hold(_PICKAXE, _TWO_HANDS)

        assert inventory.held_items() == (_PICKAXE,)
        assert set(inventory.packed_items()) == {_LANTERN, _KNIFE}
        events = inventory.get_events()
        assert [type(event) for event in events] == [ItemPutAwayEvent, ItemPutAwayEvent, ItemHeldEvent]
        assert [event.item for event in events] == [_LANTERN, _KNIFE, _PICKAXE]

    def test_holding_one_handed_item_with_full_hands_puts_away_the_first_held(self) -> None:
        """片手の物 2 つで手がふさがっているとき片手の物を持つと、先に手に持った物だけを荷にしまう。"""
        inventory = _inventory(_LANTERN, _KNIFE, _ROPE)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.hold(_KNIFE, _ONE_HAND)
        inventory.clear_events()

        inventory.hold(_ROPE, _ONE_HAND)

        assert inventory.held_items() == (_KNIFE, _ROPE)
        assert inventory.packed_items() == (_LANTERN,)
        assert [type(event) for event in inventory.get_events()] == [ItemPutAwayEvent, ItemHeldEvent]

    def test_holding_one_handed_item_while_holding_two_handed_item_puts_it_away(self) -> None:
        """両手の物を持っているとき片手の物を持つと、両手の物を荷にしまう。"""
        inventory = _inventory(_PICKAXE, _LANTERN)
        inventory.hold(_PICKAXE, _TWO_HANDS)

        inventory.hold(_LANTERN, _ONE_HAND)

        assert inventory.held_items() == (_LANTERN,)
        assert inventory.packed_items() == (_PICKAXE,)

    def test_holding_an_item_not_carried_is_refused(self) -> None:
        """持っていない品物を hold すると ItemNotCarriedException を投げ、手もイベントも変わらない。"""
        inventory = _inventory(_LANTERN)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.clear_events()

        with pytest.raises(ItemNotCarriedException):
            inventory.hold(_PICKAXE, _TWO_HANDS)

        assert inventory.held_items() == (_LANTERN,)
        assert inventory.get_events() == []

    def test_holding_an_item_already_in_hands_records_nothing(self) -> None:
        """もう手に持っている品物を hold しても断らず、手もイベントも変わらない。"""
        inventory = _inventory(_LANTERN, _KNIFE)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.hold(_KNIFE, _ONE_HAND)
        inventory.clear_events()

        inventory.hold(_LANTERN, _ONE_HAND)

        assert inventory.held_items() == (_LANTERN, _KNIFE)
        assert inventory.get_events() == []

    def test_put_away_moves_item_from_hands_to_pack(self) -> None:
        """手の物を put_away すると荷に移り、持ち主と品物を持つ ItemPutAwayEvent がたまる。"""
        inventory = _inventory(_LANTERN)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.clear_events()

        inventory.put_away(_LANTERN)

        assert inventory.held_items() == ()
        assert inventory.packed_items() == (_LANTERN,)
        [event] = inventory.get_events()
        assert isinstance(event, ItemPutAwayEvent)
        assert (event.person, event.item) == (_ALICE, _LANTERN)

    def test_putting_away_an_item_already_in_pack_records_nothing(self) -> None:
        """荷にある品物を put_away しても断らず、イベントもたまらない。"""
        inventory = _inventory(_LANTERN)

        inventory.put_away(_LANTERN)

        assert inventory.packed_items() == (_LANTERN,)
        assert inventory.get_events() == []

    def test_putting_away_an_item_not_carried_is_refused(self) -> None:
        """持っていない品物を put_away すると ItemNotCarriedException を投げる。"""
        inventory = _inventory()

        with pytest.raises(ItemNotCarriedException):
            inventory.put_away(_LANTERN)


class TestPersonInventoryGold:
    """PersonInventory の earn / pay が金を増減し、足りない支払いを断ることを保証する。"""

    def test_earn_adds_gold_and_records_before_and_after(self) -> None:
        """earn すると available_gold が増え、持ち主と前後の金額を持つ GoldEarnedEvent がたまる。"""
        inventory = _inventory()

        inventory.earn(Gold(30))

        assert inventory.available_gold() == Gold(30)
        [event] = inventory.get_events()
        assert isinstance(event, GoldEarnedEvent)
        assert (event.person, event.amount, event.before, event.after) == (_ALICE, Gold(30), Gold(0), Gold(30))

    def test_pay_takes_gold_and_records_before_and_after(self) -> None:
        """pay すると available_gold が減り、持ち主と前後の金額を持つ GoldPaidEvent がたまる。"""
        inventory = _inventory()
        inventory.earn(Gold(30))
        inventory.clear_events()

        inventory.pay(Gold(12))

        assert inventory.available_gold() == Gold(18)
        [event] = inventory.get_events()
        assert isinstance(event, GoldPaidEvent)
        assert (event.amount, event.before, event.after) == (Gold(12), Gold(30), Gold(18))

    def test_paying_more_than_available_is_refused(self) -> None:
        """持っている金より多く pay すると InsufficientGoldException を投げ、金もイベントも変わらない。"""
        inventory = _inventory()
        inventory.earn(Gold(5))
        inventory.clear_events()

        with pytest.raises(InsufficientGoldException):
            inventory.pay(Gold(6))

        assert inventory.available_gold() == Gold(5)
        assert inventory.get_events() == []

    @pytest.mark.parametrize("operation", ["earn", "pay"])
    def test_zero_gold_records_nothing(self, operation: str) -> None:
        """Gold(0) を earn / pay しても断らず、金もイベントも変わらない。"""
        inventory = _inventory()

        getattr(inventory, operation)(Gold(0))

        assert inventory.available_gold() == Gold(0)
        assert inventory.get_events() == []
