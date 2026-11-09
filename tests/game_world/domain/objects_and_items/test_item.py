from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    CountStateKind,
    CountValue,
    FlagStateKind,
    FlagValue,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    Lasts,
    LastsIndefinitely,
    LitWhen,
    NotALightSource,
)
from ai_rpg_world.game_world.domain.exception.game_world_exception import TickOrderException
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import StateValueMismatchesKindException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    ItemAlreadyLeftWorldException,
    ItemDoesNotRunOutException,
    ItemHasNotRunOutException,
    StateKeyNotOwnedException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    CarriedBy,
    Item,
    ItemCameIntoWorldEvent,
    ItemInstanceId,
    ItemLeftWorldEvent,
    ItemRanOutEvent,
    ItemStateChangedEvent,
    LyingAt,
)
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    ItemSpecId,
    PersonId,
    SpotId,
    StateKeyId,
    Ticks,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded

_LANTERN_SPEC = ItemSpecId("lantern")
_UNLIT = ChoiceName("unlit")
_LIT = ChoiceName("lit")
_WICK = ItemStateKeyDeclaration(
    item_spec_id=_LANTERN_SPEC,
    key=StateKeyId("wick"),
    kind=ChoiceStateKind(choices=(_UNLIT, _LIT)),
    initial=ChoiceValue(_UNLIT),
)
_OIL = ItemStateKeyDeclaration(
    item_spec_id=_LANTERN_SPEC,
    key=StateKeyId("oil"),
    kind=CountStateKind(),
    initial=CountValue(Count(3)),
)
_ITEM_ID = ItemInstanceId("lantern#1")
_CAME_AT = WorldTick(10)


_FLAME_LASTS = Lasts(ticks=Ticks(16), ended_text=DescriptionText("カンテラの灯が燃え尽きた。"))
_HARU = PersonId("haru")
_SHAFT = SpotId("shaft")


def _lantern(
    lights_up: LitWhen | NotALightSource = LitWhen(_WICK.key, ChoiceValue(_LIT)),
    lasts: Lasts | LastsIndefinitely = LastsIndefinitely(),
) -> ItemSpecDeclaration:
    return ItemSpecDeclaration(
        item_spec_id=_LANTERN_SPEC,
        name=DisplayName("カンテラ"),
        description=DescriptionText("油で灯る手提げの明かり"),
        state_keys=(_WICK, _OIL),
        lights_up=lights_up,
        hands_needed=HandsNeeded(1),
        lasts=lasts,
    )


def _came_into_world(spec: ItemSpecDeclaration | None = None) -> Item:
    item = Item.come_into_world(_ITEM_ID, spec or _lantern(), _CAME_AT)
    item.clear_events()
    return item


class TestItemComeIntoWorld:
    """Item.come_into_world が、品物の宣言の初めの値で品物を世界に出し、そのことをイベントにためることを保証する。"""

    def test_starts_with_declared_initial_values(self) -> None:
        """出た直後の品物は、自分の ID と品物の宣言の ID を持ち、どの鍵も宣言の initial を返す。"""
        item = Item.come_into_world(_ITEM_ID, _lantern(), _CAME_AT)

        assert item.item_id == _ITEM_ID
        assert item.spec_id == _LANTERN_SPEC
        assert item.value_of(_WICK) == ChoiceValue(_UNLIT)
        assert item.value_of(_OIL) == CountValue(Count(3))

    def test_records_came_into_world_event(self) -> None:
        """come_into_world は、品物・品物の宣言・出た時刻を持つ ItemCameIntoWorldEvent を 1 つためる。"""
        item = Item.come_into_world(_ITEM_ID, _lantern(), _CAME_AT)

        [event] = item.get_events()
        assert isinstance(event, ItemCameIntoWorldEvent)
        assert (event.item, event.spec_id, event.came_at) == (_ITEM_ID, _LANTERN_SPEC, _CAME_AT)


class TestItemSet:
    """Item.set が、種類に合う値だけを受け、変わったときに前後の値をイベントに残すことを保証する。"""

    def test_set_changes_value_and_records_before_and_after(self) -> None:
        """種類に合う値を set すると value_of がその値を返し、鍵と前後の値を持つ ItemStateChangedEvent がたまる。"""
        item = _came_into_world()

        item.set(_WICK, ChoiceValue(_LIT))

        assert item.value_of(_WICK) == ChoiceValue(_LIT)
        [event] = item.get_events()
        assert isinstance(event, ItemStateChangedEvent)
        assert (event.item, event.key, event.before, event.after) == (
            _ITEM_ID,
            _WICK.key,
            ChoiceValue(_UNLIT),
            ChoiceValue(_LIT),
        )

    def test_value_that_does_not_fit_kind_is_refused(self) -> None:
        """種類に合わない値を set すると StateValueMismatchesKindException を投げ、値もイベントも変わらない。"""
        item = _came_into_world()

        with pytest.raises(StateValueMismatchesKindException):
            item.set(_WICK, FlagValue(raised=True))

        assert item.value_of(_WICK) == ChoiceValue(_UNLIT)
        assert item.get_events() == []

    def test_key_of_another_item_spec_is_refused(self) -> None:
        """ほかの品物の宣言の鍵で set すると StateKeyNotOwnedException を投げ、イベントはたまらない。"""
        item = _came_into_world()
        foreign = ItemStateKeyDeclaration(
            item_spec_id=ItemSpecId("pickaxe"),
            key=StateKeyId("wick"),
            kind=FlagStateKind(),
            initial=FlagValue(raised=False),
        )

        with pytest.raises(StateKeyNotOwnedException):
            item.set(foreign, FlagValue(raised=True))

        assert item.get_events() == []

    def test_reading_key_of_another_item_spec_is_refused(self) -> None:
        """ほかの品物の宣言の鍵で value_of を呼ぶと StateKeyNotOwnedException を投げる。"""
        item = _came_into_world()
        foreign = ItemStateKeyDeclaration(
            item_spec_id=ItemSpecId("pickaxe"),
            key=StateKeyId("sharp"),
            kind=FlagStateKind(),
            initial=FlagValue(raised=False),
        )

        with pytest.raises(StateKeyNotOwnedException):
            item.value_of(foreign)

    def test_setting_the_same_value_records_nothing(self) -> None:
        """今と同じ値を set しても断らず、イベントもたまらない。"""
        item = _came_into_world()

        item.set(_WICK, ChoiceValue(_UNLIT))

        assert item.get_events() == []


class TestItemAge:
    """Item.age が、世界に出た時刻からの経過を返すことを保証する。"""

    def test_age_is_ticks_since_it_came_into_world(self) -> None:
        """出た時刻が 10 で now が 25 のとき、Ticks(15) を返す。"""
        item = _came_into_world()

        assert item.age(WorldTick(25)) == Ticks(15)

    def test_now_before_it_came_into_world_is_refused(self) -> None:
        """出た時刻より前の now を渡すと TickOrderException を投げる。"""
        item = _came_into_world()

        with pytest.raises(TickOrderException):
            item.age(WorldTick(9))


class TestItemGivesLight:
    """Item.gives_light が、品物の宣言の lights_up が指す鍵の今の値で灯っているかを決めることを保証する。"""

    def test_lit_when_the_key_has_the_declared_value(self) -> None:
        """LitWhen の鍵が LitWhen の値になると True を返し、それまでは False を返す。"""
        item = _came_into_world()
        assert not item.gives_light()

        item.set(_WICK, ChoiceValue(_LIT))

        assert item.gives_light()

    def test_not_a_light_source_never_gives_light(self) -> None:
        """lights_up が NotALightSource の品物は、どの値でも False を返す。"""
        item = _came_into_world(_lantern(lights_up=NotALightSource()))

        item.set(_WICK, ChoiceValue(_LIT))

        assert not item.gives_light()


class TestItemLeaveWorld:
    """Item.leave_world が品物を世界から外し、外れた品物の状態を変えさせないことを保証する。"""

    def test_leave_world_records_event(self) -> None:
        """leave_world は、品物の ID を持つ ItemLeftWorldEvent を 1 つためる。"""
        item = _came_into_world()

        item.leave_world()

        [event] = item.get_events()
        assert isinstance(event, ItemLeftWorldEvent)
        assert event.item == _ITEM_ID

    def test_set_after_leaving_world_is_refused(self) -> None:
        """世界から外れた品物に set すると ItemAlreadyLeftWorldException を投げ、値もイベントも変わらない。"""
        item = _came_into_world()
        item.leave_world()
        item.clear_events()

        with pytest.raises(ItemAlreadyLeftWorldException):
            item.set(_WICK, ChoiceValue(_LIT))

        assert item.value_of(_WICK) == ChoiceValue(_UNLIT)
        assert item.get_events() == []

    def test_leaving_twice_records_nothing(self) -> None:
        """世界から外れた品物にもう一度 leave_world を呼んでも断らず、イベントもたまらない。"""
        item = _came_into_world()
        item.leave_world()
        item.clear_events()

        item.leave_world()

        assert item.get_events() == []


class TestItemRunOut:
    """Item.run_out が、宣言の Lasts の時間が過ぎた品物だけを、どこにあったかを添えて世界から出すことを保証する。"""

    def test_before_its_time_is_refused_and_records_nothing(self) -> None:
        """ticks: 16 の灯が世界に出て 15 tick のとき run_out すると ItemHasNotRunOutException を投げ、イベントはたまらず、品物は世界に残る。"""
        item = _came_into_world(_lantern(lasts=_FLAME_LASTS))

        with pytest.raises(ItemHasNotRunOutException):
            item.run_out(WorldTick(25), CarriedBy(_HARU))

        assert item.get_events() == []
        item.set(_WICK, ChoiceValue(_LIT))

    def test_carried_item_runs_out_with_its_holder(self) -> None:
        """ticks: 16 の灯が世界に出て 16 tick のとき CarriedBy(haru) で run_out すると、品物・宣言・持ち主・時刻を持つ ItemRanOutEvent を 1 つだけためる。"""
        item = _came_into_world(_lantern(lasts=_FLAME_LASTS))

        item.run_out(WorldTick(26), CarriedBy(_HARU))

        [event] = item.get_events()
        assert isinstance(event, ItemRanOutEvent)
        assert (event.item, event.spec_id, event.where, event.at) == (
            _ITEM_ID,
            _LANTERN_SPEC,
            CarriedBy(_HARU),
            WorldTick(26),
        )

    def test_item_lying_on_the_ground_runs_out_with_its_spot(self) -> None:
        """地面にある灯を LyingAt(shaft) で run_out すると、ItemRanOutEvent の where がその場所になる。"""
        item = _came_into_world(_lantern(lasts=_FLAME_LASTS))

        item.run_out(WorldTick(40), LyingAt(_SHAFT))

        [event] = item.get_events()
        assert isinstance(event, ItemRanOutEvent)
        assert event.where == LyingAt(_SHAFT)

    def test_item_that_ran_out_has_left_the_world(self) -> None:
        """run_out した品物に set すると ItemAlreadyLeftWorldException を投げる。"""
        item = _came_into_world(_lantern(lasts=_FLAME_LASTS))
        item.run_out(WorldTick(26), CarriedBy(_HARU))

        with pytest.raises(ItemAlreadyLeftWorldException):
            item.set(_WICK, ChoiceValue(_LIT))

    def test_item_that_lasts_indefinitely_is_refused(self) -> None:
        """LastsIndefinitely の品物に run_out すると ItemDoesNotRunOutException を投げ、イベントはたまらない。"""
        item = _came_into_world(_lantern(lasts=LastsIndefinitely()))

        with pytest.raises(ItemDoesNotRunOutException):
            item.run_out(WorldTick(1000), CarriedBy(_HARU))

        assert item.get_events() == []

    def test_item_that_already_left_records_nothing(self) -> None:
        """世界から外れた品物に run_out しても断らず、イベントもたまらない。"""
        item = _came_into_world(_lantern(lasts=_FLAME_LASTS))
        item.leave_world()
        item.clear_events()

        item.run_out(WorldTick(26), CarriedBy(_HARU))

        assert item.get_events() == []
