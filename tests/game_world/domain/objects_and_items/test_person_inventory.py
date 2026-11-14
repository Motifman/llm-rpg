from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    InsufficientGoldException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    InventoryFullException,
    ItemAlreadyCarriedException,
    ItemNotCarriedException,
    NotEnoughItemsOfSpecException,
)
from ai_rpg_world.game_world.domain.exception.person_inventory_exception import (
    HeldItemsExceedHandsException,
    ItemNotHeldException,
    ItemNotPackedException,
    PackIsEmptyException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    GoldEarnedEvent,
    GoldPaidEvent,
    HeldItem,
    ItemGivenUpEvent,
    ItemHeldEvent,
    ItemInstanceId,
    ItemPutAwayEvent,
    ItemReceivedEvent,
    PackedItem,
    PersonInventory,
    PersonInventoryMemento,
)
from ai_rpg_world.game_world.domain.value_object import Capacity, Count, Gold, HandsNeeded, ItemSpecId, PersonId
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot
from tests.game_world.support.world_in_memory import FractionsInOrder

_ALICE = PersonId("alice")
_LANTERN = ItemInstanceId("lantern#1")
_KNIFE = ItemInstanceId("knife#1")
_ROPE = ItemInstanceId("rope#1")
_PICKAXE = ItemInstanceId("pickaxe#1")
_APPLE = ItemSpecId("apple")
_APPLE_1 = ItemInstanceId("apple#1")
_APPLE_2 = ItemInstanceId("apple#2")
_APPLE_3 = ItemInstanceId("apple#3")
_ONE_HAND = HandsNeeded(1)
_TWO_HANDS = HandsNeeded(2)
_DESIGN = compose_world(nouns(spots=(spot("square"),), characters=(character("alice", "square"),)))


def _spec_of(item: ItemInstanceId) -> ItemSpecId:
    return ItemSpecId(item.value.split("#")[0])


def _inventory(*items: ItemInstanceId, capacity: int = 10) -> PersonInventory:
    inventory = PersonInventory.start(_ALICE, Capacity(capacity))
    for item in items:
        inventory.receive(item, _spec_of(item))
    inventory.clear_events()
    return inventory


class TestPersonInventoryReceiveAndGiveUp:
    """PersonInventory の receive / give_up が、品物を荷に入れ、手の物でも荷の物でも手放させることを保証する。"""

    def test_starts_empty_for_its_person(self) -> None:
        """作った直後は自分の人の ID を持ち、品物も金も無く、満杯でもない。"""
        inventory = PersonInventory.start(_ALICE, Capacity(2))

        assert inventory.person_id == _ALICE
        assert inventory.items() == ()
        assert inventory.available_gold() == Gold(0)
        assert not inventory.is_full()

    def test_receive_puts_item_in_pack_and_records_event(self) -> None:
        """receive した品物は荷に入り、手には無く、持ち主と品物を持つ ItemReceivedEvent がたまる。"""
        inventory = _inventory()

        inventory.receive(_LANTERN, _spec_of(_LANTERN))

        assert inventory.packed_items() == (_LANTERN,)
        assert inventory.held_items() == ()
        [event] = inventory.get_events()
        assert isinstance(event, ItemReceivedEvent)
        assert (event.person, event.item) == (_ALICE, _LANTERN)

    def test_receiving_an_item_already_carried_is_refused(self) -> None:
        """もう持っている品物を receive すると ItemAlreadyCarriedException を投げ、イベントはたまらない。"""
        inventory = _inventory(_LANTERN)

        with pytest.raises(ItemAlreadyCarriedException):
            inventory.receive(_LANTERN, _spec_of(_LANTERN))

        assert inventory.items() == (_LANTERN,)
        assert inventory.get_events() == []

    def test_is_full_counts_held_items_too(self) -> None:
        """手に持った物も数に入れ、品物の数が上限に達すると is_full が True を返す。"""
        inventory = _inventory(_LANTERN, capacity=2)
        inventory.hold(_LANTERN, _ONE_HAND)
        assert not inventory.is_full()

        inventory.receive(_KNIFE, _spec_of(_KNIFE))

        assert inventory.is_full()

    def test_receiving_when_full_is_refused(self) -> None:
        """満杯のときに receive すると InventoryFullException を投げ、品物もイベントも増えない。"""
        inventory = _inventory(_LANTERN, _KNIFE, capacity=2)

        with pytest.raises(InventoryFullException):
            inventory.receive(_ROPE, _spec_of(_ROPE))

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


class TestPersonInventoryItemsBySpec:
    """PersonInventory が receive で覚えた品物の種類で、持っている数を数え、手放す品物を選ぶことを保証する。"""

    def test_count_of_counts_received_items_of_the_spec(self) -> None:
        """りんご 2 つとカンテラ 1 つを receive すると、count_of(りんご) は 2 を答える。"""
        inventory = _inventory(_APPLE_1, _LANTERN, _APPLE_2)

        assert inventory.count_of(_APPLE) == Count(2)

    def test_count_of_includes_held_items(self) -> None:
        """手に持ったりんごも count_of に数えられる。"""
        inventory = _inventory(_APPLE_1, _APPLE_2)
        inventory.hold(_APPLE_1, _ONE_HAND)

        assert inventory.count_of(_APPLE) == Count(2)

    def test_count_of_spec_never_received_is_zero(self) -> None:
        """一度も受け取っていない種類の count_of は 0 を答える。"""
        inventory = _inventory(_LANTERN)

        assert inventory.count_of(_APPLE) == Count(0)

    def test_given_up_item_is_no_longer_counted(self) -> None:
        """りんごを 1 つ give_up すると、count_of(りんご) は 1 つ減る。"""
        inventory = _inventory(_APPLE_1, _APPLE_2)

        inventory.give_up(_APPLE_1)

        assert inventory.count_of(_APPLE) == Count(1)

    def test_items_to_give_up_takes_from_pack_first_then_hands(self) -> None:
        """手にりんご 1 つ、荷にりんご 2 つのとき、items_to_give_up(りんご, 3) は荷の 2 つを先に、手の 1 つを最後に選ぶ。"""
        inventory = _inventory(_APPLE_1, _APPLE_2, _APPLE_3)
        inventory.hold(_APPLE_1, _ONE_HAND)

        chosen = inventory.items_to_give_up(_APPLE, Count(3))

        assert chosen == (_APPLE_2, _APPLE_3, _APPLE_1)

    def test_items_to_give_up_leaves_held_items_when_pack_is_enough(self) -> None:
        """荷のりんごで足りるとき、items_to_give_up は手のりんごを選ばない。"""
        inventory = _inventory(_APPLE_1, _APPLE_2, _APPLE_3)
        inventory.hold(_APPLE_1, _ONE_HAND)

        chosen = inventory.items_to_give_up(_APPLE, Count(2))

        assert chosen == (_APPLE_2, _APPLE_3)

    def test_items_to_give_up_skips_other_specs(self) -> None:
        """荷にカンテラが先に入っていても、items_to_give_up(りんご, 1) はりんごだけを選ぶ。"""
        inventory = _inventory(_LANTERN, _APPLE_1)

        assert inventory.items_to_give_up(_APPLE, Count(1)) == (_APPLE_1,)

    def test_items_to_give_up_refuses_when_too_few_and_changes_nothing(self) -> None:
        """りんごを 2 つしか持たないのに 3 つ求めると NotEnoughItemsOfSpecException を投げ、持ち物もイベントも変わらない。"""
        inventory = _inventory(_APPLE_1, _APPLE_2)

        with pytest.raises(NotEnoughItemsOfSpecException):
            inventory.items_to_give_up(_APPLE, Count(3))

        assert inventory.items() == (_APPLE_1, _APPLE_2)
        assert inventory.get_events() == []


class TestPersonInventoryRandomPackedItem:
    """PersonInventory.random_packed_item が、引いた偶然で荷の物から 1 つを選び、手の物を選ばないことを保証する。"""

    @pytest.mark.parametrize(
        ("fraction", "expected"),
        [(0.0, _LANTERN), (0.34, _KNIFE), (0.99, _ROPE)],
    )
    def test_chooses_packed_item_by_fraction_in_packing_order(self, fraction: float, expected: ItemInstanceId) -> None:
        """荷にカンテラ・ナイフ・縄が入った順に並ぶとき、引いた値が [0, 1/3) ならカンテラ、[1/3, 2/3) ならナイフ、[2/3, 1) なら縄を選ぶ。"""
        inventory = _inventory(_LANTERN, _KNIFE, _ROPE)

        chosen = inventory.random_packed_item(FractionsInOrder((fraction,)))

        assert chosen == expected

    def test_never_chooses_held_item(self) -> None:
        """カンテラを手に持ち、荷に縄だけがあるとき、引いた値が 0 でも縄を選ぶ。"""
        inventory = _inventory(_LANTERN, _ROPE)
        inventory.hold(_LANTERN, _ONE_HAND)

        chosen = inventory.random_packed_item(FractionsInOrder((0.0,)))

        assert chosen == _ROPE

    def test_choosing_changes_nothing(self) -> None:
        """選ぶだけでは手放さない。持ち物はそのままで、イベントも出ない。"""
        inventory = _inventory(_LANTERN, _ROPE)

        inventory.random_packed_item(FractionsInOrder((0.5,)))

        assert inventory.items() == (_LANTERN, _ROPE)
        assert inventory.get_events() == []

    def test_refuses_when_pack_is_empty_even_if_hands_hold_something(self) -> None:
        """荷が空なら、手にカンテラを持っていても PackIsEmptyException を投げ、偶然も引かない。"""
        inventory = _inventory(_LANTERN)
        inventory.hold(_LANTERN, _ONE_HAND)
        random = FractionsInOrder((0.5,))

        with pytest.raises(PackIsEmptyException):
            inventory.random_packed_item(random)

        assert random.next_fraction() == 0.5


class TestPersonInventoryGiveUpFromHandsOrPack:
    """PersonInventory.give_up_held / give_up_packed が、指した場所にある物だけを手放させることを保証する。"""

    def test_give_up_held_releases_item_in_hands(self) -> None:
        """手に持つカンテラを give_up_held すると持ち物から消え、was_held が真の ItemGivenUpEvent を出す。"""
        inventory = _inventory(_LANTERN, _ROPE)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.clear_events()

        inventory.give_up_held(_LANTERN)

        assert inventory.items() == (_ROPE,)
        events = inventory.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemGivenUpEvent)
        assert events[0].item == _LANTERN
        assert events[0].was_held

    def test_give_up_held_refuses_packed_item_and_changes_nothing(self) -> None:
        """荷にある縄を give_up_held すると ItemNotHeldException を投げ、持ち物もイベントも変わらない。"""
        inventory = _inventory(_ROPE)

        with pytest.raises(ItemNotHeldException):
            inventory.give_up_held(_ROPE)

        assert inventory.items() == (_ROPE,)
        assert inventory.get_events() == []

    def test_give_up_held_refuses_item_not_carried(self) -> None:
        """持っていない縄を give_up_held すると ItemNotCarriedException を投げる。"""
        inventory = _inventory()

        with pytest.raises(ItemNotCarriedException):
            inventory.give_up_held(_ROPE)

    def test_give_up_packed_releases_item_in_pack(self) -> None:
        """荷にある縄を give_up_packed すると持ち物から消え、was_held が偽の ItemGivenUpEvent を出す。"""
        inventory = _inventory(_ROPE)

        inventory.give_up_packed(_ROPE)

        assert inventory.items() == ()
        events = inventory.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemGivenUpEvent)
        assert not events[0].was_held

    def test_give_up_packed_refuses_held_item_and_changes_nothing(self) -> None:
        """手に持つカンテラを give_up_packed すると ItemNotPackedException を投げ、持ち物もイベントも変わらない。"""
        inventory = _inventory(_LANTERN)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.clear_events()

        with pytest.raises(ItemNotPackedException):
            inventory.give_up_packed(_LANTERN)

        assert inventory.items() == (_LANTERN,)
        assert inventory.get_events() == []

    def test_give_up_packed_refuses_item_not_carried(self) -> None:
        """持っていない縄を give_up_packed すると ItemNotCarriedException を投げる。"""
        inventory = _inventory()

        with pytest.raises(ItemNotCarriedException):
            inventory.give_up_packed(_ROPE)


class TestPersonInventoryMemento:
    """PersonInventory を memento から作り直すと、手と荷の品物とその順・品物の種類・金・入る数が元と同じで、イベントは出ず、宣言に無い人の持ち物は読まないことを保証する。"""

    def _carrying_knife_and_lantern_in_hands(self) -> PersonInventory:
        inventory = _inventory(_KNIFE, _LANTERN, _APPLE_1, _APPLE_2, capacity=4)
        inventory.hold(_KNIFE, _ONE_HAND)
        inventory.hold(_LANTERN, _ONE_HAND)
        inventory.earn(Gold(30))
        inventory.pay(Gold(5))
        return inventory

    def test_rebuilt_inventory_keeps_hands_pack_gold_and_capacity(self) -> None:
        """ナイフとカンテラを手に、りんご 2 つを荷に持ち、30 稼いで 5 払ったあと作り直すと、どれも同じで、4 つで満杯。"""
        inventory = self._carrying_knife_and_lantern_in_hands()

        rebuilt = rebuilt_from_memento(inventory, _DESIGN.nouns)

        assert rebuilt.memento() == inventory.memento()
        assert rebuilt.memento() != PersonInventory.start(_ALICE, Capacity(4)).memento()
        assert rebuilt.person_id == _ALICE
        assert rebuilt.held_items() == (_KNIFE, _LANTERN)
        assert rebuilt.packed_items() == (_APPLE_1, _APPLE_2)
        assert rebuilt.count_of(_APPLE) == Count(2)
        assert rebuilt.available_gold() == Gold(25)
        assert rebuilt.is_full()

    def test_rebuilt_inventory_puts_away_the_first_held_item_first(self) -> None:
        """両手がふさがった持ち物を作り直してから片手の物を持つと、先に持ったナイフが荷に戻り、カンテラは手に残る。"""
        inventory = self._carrying_knife_and_lantern_in_hands()
        rebuilt = rebuilt_from_memento(inventory, _DESIGN.nouns)

        rebuilt.hold(_APPLE_1, _ONE_HAND)

        assert rebuilt.held_items() == (_LANTERN, _APPLE_1)
        assert _KNIFE in rebuilt.packed_items()

    def test_rebuilding_records_no_event(self) -> None:
        """品物を持って金を稼いだあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        inventory = self._carrying_knife_and_lantern_in_hands()

        assert rebuilt_from_memento(inventory, _DESIGN.nouns).get_events() == []

    def test_same_item_held_and_packed_is_refused(self) -> None:
        """カンテラを手と荷の両方に持つ memento を作ると、RepeatedMementoKeyException を投げる。"""
        lantern_spec = ItemSpecId("lantern")

        with pytest.raises(RepeatedMementoKeyException):
            PersonInventoryMemento(
                person_id=_ALICE,
                capacity=Capacity(4),
                gold=Gold(0),
                held=(HeldItem(_LANTERN, lantern_spec, _ONE_HAND),),
                packed=(PackedItem(_LANTERN, lantern_spec),),
            )

    def test_inventory_of_undeclared_person_is_refused(self) -> None:
        """宣言に無い carol の持ち物の memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = PersonInventoryMemento(
            person_id=PersonId("carol"),
            capacity=Capacity(4),
            gold=Gold(0),
            held=(),
            packed=(PackedItem(_LANTERN, ItemSpecId("lantern")),),
        )

        with pytest.raises(UndeclaredNounException):
            PersonInventory.from_memento(memento, _DESIGN.nouns)


class TestPersonInventoryStartsOnlyInReachableState:
    """PersonInventory は、受け取る・持つの操作では作れない持ち方から始まらないことを保証する。"""

    def test_three_items_in_two_hands_are_refused(self) -> None:
        """片手で持つ物 3 つを手に持つ memento から作り直すと、HeldItemsExceedHandsException を投げる。"""
        memento = PersonInventoryMemento(
            person_id=_ALICE,
            capacity=Capacity(5),
            gold=Gold(0),
            held=tuple(HeldItem(item, _APPLE, _ONE_HAND) for item in (_KNIFE, _LANTERN, _ROPE)),
            packed=(),
        )

        with pytest.raises(HeldItemsExceedHandsException):
            PersonInventory.from_memento(memento, _DESIGN.nouns)

    def test_more_items_than_capacity_are_refused(self) -> None:
        """入る数が 2 の持ち物に 3 つ入っている memento から作り直すと、InventoryFullException を投げる。"""
        memento = PersonInventoryMemento(
            person_id=_ALICE,
            capacity=Capacity(2),
            gold=Gold(0),
            held=(),
            packed=tuple(PackedItem(item, _APPLE) for item in (_KNIFE, _LANTERN, _ROPE)),
        )

        with pytest.raises(InventoryFullException):
            PersonInventory.from_memento(memento, _DESIGN.nouns)

    def test_as_many_items_as_capacity_are_accepted(self) -> None:
        """入る数が 3 の持ち物にちょうど 3 つ入っている memento からは作り直せ、満杯になる。"""
        memento = PersonInventoryMemento(
            person_id=_ALICE,
            capacity=Capacity(3),
            gold=Gold(0),
            held=(),
            packed=tuple(PackedItem(item, _APPLE) for item in (_KNIFE, _LANTERN, _ROPE)),
        )

        assert PersonInventory.from_memento(memento, _DESIGN.nouns).is_full()

    def test_same_item_held_and_packed_is_refused_by_constructor(self) -> None:
        """カンテラを手と荷の両方に持たせて直に作ると、ItemAlreadyCarriedException を投げる。"""
        with pytest.raises(ItemAlreadyCarriedException):
            PersonInventory(
                _ALICE,
                Capacity(4),
                gold=Gold(0),
                held=(HeldItem(_LANTERN, _APPLE, _ONE_HAND),),
                packed=(PackedItem(_LANTERN, _APPLE),),
            )
