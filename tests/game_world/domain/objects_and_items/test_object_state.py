from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    CountStateKind,
    CountValue,
    FlagStateKind,
    FlagValue,
    NoRefill,
    NothingWritten,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateKind,
    StateValue,
    StockStateKind,
    StockValue,
    TextBody,
    WrittenText,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.exception.game_world_exception import CountBelowZeroException, TickOrderException
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import StateValueMismatchesKindException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    NotEnoughStockException,
    OperationNotForStateKindException,
    StateKeyNotOwnedException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    ObjectRevealedEvent,
    ObjectState,
    ObjectStateChangedEvent,
    TextWrittenEvent,
)
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    ObjectId,
    PersonId,
    SpotId,
    StateKeyId,
    Ticks,
    WorldTick,
)

_WELL = ObjectId("well")
_ALICE = PersonId("alice")
_START = WorldTick(0)


def _key(key: str, kind: StateKind, initial: StateValue, object_id: ObjectId = _WELL) -> ObjectStateKeyDeclaration:
    return ObjectStateKeyDeclaration(object_id=object_id, key=StateKeyId(key), kind=kind, initial=initial)


_COVERED = _key("covered", FlagStateKind(), FlagValue(raised=True))
_BUCKETS = _key("buckets", CountStateKind(), CountValue(Count(2)))
_NOTE = _key("note", WrittenTextStateKind(), NothingWritten())


def _water(
    capacity: int = 5, initial: int = 0, refills_every: Ticks | NoRefill = Ticks(3)
) -> ObjectStateKeyDeclaration:
    return _key(
        "water",
        StockStateKind(capacity=Count(capacity), refills_every=refills_every),
        StockValue(Count(initial)),
    )


def _well(*state_keys: ObjectStateKeyDeclaration, hidden: bool = False) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=_WELL,
        spot_id=SpotId("square"),
        name=DisplayName("井戸"),
        description=DescriptionText("石を積んだ古い井戸"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=hidden),
        state_keys=state_keys or (_COVERED, _BUCKETS, _NOTE),
    )


def _opened(declaration: ObjectDeclaration | None = None, now: WorldTick = _START) -> ObjectState:
    state = ObjectState.from_declaration(declaration or _well(), now)
    state.clear_events()
    return state


class TestObjectStateFromDeclaration:
    """ObjectState.from_declaration が、物の宣言の初めの値と見え方で状態を作ることを保証する。"""

    def test_starts_with_declared_initial_values(self) -> None:
        """作った直後は物の ID を持ち、どの鍵も宣言の initial を返し、イベントはたまっていない。"""
        state = ObjectState.from_declaration(_well(), _START)

        assert state.object_id == _WELL
        assert state.value_of(_COVERED, _START) == FlagValue(raised=True)
        assert state.value_of(_BUCKETS, _START) == CountValue(Count(2))
        assert state.value_of(_NOTE, _START) == NothingWritten()
        assert state.get_events() == []

    @pytest.mark.parametrize(("hidden", "revealed"), [(True, False), (False, True)])
    def test_revealed_unless_hidden_until_revealed(self, hidden: bool, revealed: bool) -> None:
        """hidden_until_revealed の物は現れていない状態で開き、そうでない物は初めから現れている。"""
        state = ObjectState.from_declaration(_well(hidden=hidden), _START)

        assert state.is_revealed() is revealed


class TestObjectStateSet:
    """ObjectState.set が種類に合う値だけを受け、変わったときに前後の値をイベントに残すことを保証する。"""

    def test_set_changes_value_and_records_before_and_after(self) -> None:
        """種類に合う値を set すると value_of がその値を返し、物・鍵・前後の値を持つ ObjectStateChangedEvent がたまる。"""
        state = _opened()

        state.set(_COVERED, FlagValue(raised=False), WorldTick(4))

        assert state.value_of(_COVERED, WorldTick(4)) == FlagValue(raised=False)
        [event] = state.get_events()
        assert isinstance(event, ObjectStateChangedEvent)
        assert (event.object_id, event.key, event.before, event.after) == (
            _WELL,
            _COVERED.key,
            FlagValue(raised=True),
            FlagValue(raised=False),
        )

    def test_value_that_does_not_fit_kind_is_refused(self) -> None:
        """種類に合わない値を set すると StateValueMismatchesKindException を投げ、値もイベントも変わらない。"""
        state = _opened()

        with pytest.raises(StateValueMismatchesKindException):
            state.set(_COVERED, CountValue(Count(1)), _START)

        assert state.value_of(_COVERED, _START) == FlagValue(raised=True)
        assert state.get_events() == []

    def test_key_of_another_object_is_refused(self) -> None:
        """ほかの物の鍵で set すると StateKeyNotOwnedException を投げ、イベントはたまらない。"""
        state = _opened()
        foreign = _key("covered", FlagStateKind(), FlagValue(raised=True), object_id=ObjectId("gate"))

        with pytest.raises(StateKeyNotOwnedException):
            state.set(foreign, FlagValue(raised=False), _START)

        assert state.get_events() == []

    def test_setting_the_same_value_records_nothing(self) -> None:
        """今と同じ値を set しても断らず、イベントもたまらない。"""
        state = _opened()

        state.set(_COVERED, FlagValue(raised=True), _START)

        assert state.get_events() == []


class TestObjectStateCount:
    """ObjectState の add_to_count / subtract_from_count が数の鍵だけを足し引きし、0 を下回らせないことを保証する。"""

    def test_add_to_count_adds_and_records_before_and_after(self) -> None:
        """add_to_count すると数が増え、前後の値を持つ ObjectStateChangedEvent がたまる。"""
        state = _opened()

        state.add_to_count(_BUCKETS, Count(3))

        assert state.value_of(_BUCKETS, _START) == CountValue(Count(5))
        [event] = state.get_events()
        assert isinstance(event, ObjectStateChangedEvent)
        assert (event.before, event.after) == (CountValue(Count(2)), CountValue(Count(5)))

    def test_subtract_from_count_subtracts(self) -> None:
        """subtract_from_count すると数が減り、前後の値を持つ ObjectStateChangedEvent がたまる。"""
        state = _opened()

        state.subtract_from_count(_BUCKETS, Count(2))

        assert state.value_of(_BUCKETS, _START) == CountValue(Count(0))
        [event] = state.get_events()
        assert isinstance(event, ObjectStateChangedEvent)
        assert (event.before, event.after) == (CountValue(Count(2)), CountValue(Count(0)))

    def test_subtracting_below_zero_is_refused(self) -> None:
        """subtract_from_count で 0 を下回ると CountBelowZeroException を投げ、値もイベントも変わらない。"""
        state = _opened()

        with pytest.raises(CountBelowZeroException):
            state.subtract_from_count(_BUCKETS, Count(3))

        assert state.value_of(_BUCKETS, _START) == CountValue(Count(2))
        assert state.get_events() == []

    @pytest.mark.parametrize("operation", ["add_to_count", "subtract_from_count"])
    def test_count_operation_on_other_kind_is_refused(self, operation: str) -> None:
        """数でない鍵に add_to_count / subtract_from_count を呼ぶと OperationNotForStateKindException を投げる。"""
        state = _opened()

        with pytest.raises(OperationNotForStateKindException):
            getattr(state, operation)(_COVERED, Count(1))

        assert state.get_events() == []

    def test_adding_zero_records_nothing(self) -> None:
        """Count(0) を add_to_count しても断らず、イベントもたまらない。"""
        state = _opened()

        state.add_to_count(_BUCKETS, Count(0))

        assert state.get_events() == []


class TestObjectStateStock:
    """ObjectState の在庫の鍵が、取られた分だけ減り、refills_every ごとに 1 つずつ capacity まで戻ることを保証する。"""

    def test_take_from_stock_takes_and_records_before_and_after(self) -> None:
        """take_from_stock すると在庫が減り、前後の在庫を持つ ObjectStateChangedEvent がたまる。"""
        water = _water(initial=5)
        state = _opened(_well(water))

        state.take_from_stock(water, Count(2), WorldTick(1))

        assert state.value_of(water, WorldTick(1)) == StockValue(Count(3))
        [event] = state.get_events()
        assert isinstance(event, ObjectStateChangedEvent)
        assert (event.key, event.before, event.after) == (water.key, StockValue(Count(5)), StockValue(Count(3)))

    def test_taking_more_than_stock_is_refused(self) -> None:
        """在庫より多く take_from_stock すると NotEnoughStockException を投げ、在庫もイベントも変わらない。"""
        water = _water(initial=2, refills_every=NoRefill())
        state = _opened(_well(water))

        with pytest.raises(NotEnoughStockException):
            state.take_from_stock(water, Count(3), WorldTick(1))

        assert state.value_of(water, WorldTick(1)) == StockValue(Count(2))
        assert state.get_events() == []

    def test_take_from_stock_on_other_kind_is_refused(self) -> None:
        """在庫でない鍵に take_from_stock を呼ぶと OperationNotForStateKindException を投げる。"""
        state = _opened()

        with pytest.raises(OperationNotForStateKindException):
            state.take_from_stock(_BUCKETS, Count(1), _START)

    def test_stock_refills_one_per_interval_up_to_capacity(self) -> None:
        """在庫 0・上限 2・3 tick ごとの補充で作ると、2 tick 後は 0、3 tick 後は 1、6 tick 後は 2、それ以降も 2 を返す。"""
        water = _water(capacity=2, initial=0, refills_every=Ticks(3))
        state = _opened(_well(water))

        assert state.value_of(water, WorldTick(2)) == StockValue(Count(0))
        assert state.value_of(water, WorldTick(3)) == StockValue(Count(1))
        assert state.value_of(water, WorldTick(6)) == StockValue(Count(2))
        assert state.value_of(water, WorldTick(30)) == StockValue(Count(2))

    def test_refill_counts_from_the_tick_it_was_opened(self) -> None:
        """tick 100 に作った在庫 0 の物は、tick 102 では 0、tick 103 で 1 を返す。"""
        water = _water(initial=0, refills_every=Ticks(3))
        state = _opened(_well(water), now=WorldTick(100))

        assert state.value_of(water, WorldTick(102)) == StockValue(Count(0))
        assert state.value_of(water, WorldTick(103)) == StockValue(Count(1))

    def test_refill_progress_carries_over_a_take(self) -> None:
        """3 tick ごとの補充で、tick 4 に 1 つ取っても tick 3 から数えた端数は残り、tick 6 に 1 つ戻る。"""
        water = _water(initial=0, refills_every=Ticks(3))
        state = _opened(_well(water))

        state.take_from_stock(water, Count(1), WorldTick(4))

        assert state.value_of(water, WorldTick(5)) == StockValue(Count(0))
        assert state.value_of(water, WorldTick(6)) == StockValue(Count(1))

    def test_refill_restarts_when_taken_from_full_stock(self) -> None:
        """満杯の在庫から tick 10 に取ると、そこから数えて tick 12 では戻らず、tick 13 に 1 つ戻る。"""
        water = _water(capacity=2, initial=2, refills_every=Ticks(3))
        state = _opened(_well(water))

        state.take_from_stock(water, Count(1), WorldTick(10))

        assert state.value_of(water, WorldTick(12)) == StockValue(Count(1))
        assert state.value_of(water, WorldTick(13)) == StockValue(Count(2))

    def test_set_restarts_refill_count_at_now(self) -> None:
        """tick 5 に在庫を 0 に set すると、補充は tick 5 から数え直し、tick 7 では 0、tick 8 で 1 を返す。"""
        water = _water(initial=0, refills_every=Ticks(3))
        state = _opened(_well(water))

        state.set(water, StockValue(Count(0)), WorldTick(5))

        assert state.value_of(water, WorldTick(7)) == StockValue(Count(0))
        assert state.value_of(water, WorldTick(8)) == StockValue(Count(1))

    def test_take_records_refilled_amount_as_before(self) -> None:
        """在庫 0 から 2 つ戻ったあとに 1 つ取ると、ObjectStateChangedEvent の before は戻ったあとの 2 になる。"""
        water = _water(initial=0, refills_every=Ticks(3))
        state = _opened(_well(water))

        state.take_from_stock(water, Count(1), WorldTick(6))

        [event] = state.get_events()
        assert isinstance(event, ObjectStateChangedEvent)
        assert (event.before, event.after) == (StockValue(Count(2)), StockValue(Count(1)))

    def test_taking_zero_records_nothing(self) -> None:
        """在庫が 0 でも Count(0) の take_from_stock は断らず、在庫もイベントも変わらない。"""
        water = _water(initial=0, refills_every=NoRefill())
        state = _opened(_well(water))

        state.take_from_stock(water, Count(0), WorldTick(1))

        assert state.value_of(water, WorldTick(1)) == StockValue(Count(0))
        assert state.get_events() == []

    def test_setting_the_same_stock_does_not_restart_refill_count(self) -> None:
        """tick 5 に戻った分と同じ在庫 1 を set しても数え直さず、tick 0 から数えて tick 6 に 2 を返す。"""
        water = _water(initial=0, refills_every=Ticks(3))
        state = _opened(_well(water))

        state.set(water, StockValue(Count(1)), WorldTick(5))

        assert state.value_of(water, WorldTick(6)) == StockValue(Count(2))
        assert state.get_events() == []

    def test_no_refill_never_grows(self) -> None:
        """refills_every が NoRefill の在庫は、時が経っても増えない。"""
        water = _water(initial=1, refills_every=NoRefill())
        state = _opened(_well(water))

        assert state.value_of(water, WorldTick(1000)) == StockValue(Count(1))

    def test_reading_before_refill_count_started_is_refused(self) -> None:
        """補充を数え始めた tick より前の now で value_of を呼ぶと TickOrderException を投げる。"""
        water = _water(initial=0, refills_every=Ticks(3))
        state = _opened(_well(water), now=WorldTick(10))

        with pytest.raises(TickOrderException):
            state.value_of(water, WorldTick(9))

    def test_taking_before_refill_count_started_is_refused(self) -> None:
        """補充を数え始めた tick より前の now で take_from_stock を呼ぶと TickOrderException を投げ、在庫もイベントも変わらない。"""
        water = _water(initial=2, refills_every=Ticks(3))
        state = _opened(_well(water), now=WorldTick(10))

        with pytest.raises(TickOrderException):
            state.take_from_stock(water, Count(1), WorldTick(9))

        assert state.value_of(water, WorldTick(10)) == StockValue(Count(2))
        assert state.get_events() == []


class TestObjectStateWriteText:
    """ObjectState.write_text が、書いた文の鍵に本文・書いた人・時刻を残すことを保証する。"""

    def test_write_text_records_text_and_event(self) -> None:
        """write_text すると value_of が WrittenText を返し、前後の値を持つ TextWrittenEvent がたまる。"""
        state = _opened()
        body = TextBody("水は濁っている")

        state.write_text(_NOTE, body, _ALICE, WorldTick(7))

        written = WrittenText(body=body, author=_ALICE, written_at=WorldTick(7))
        assert state.value_of(_NOTE, WorldTick(7)) == written
        [event] = state.get_events()
        assert isinstance(event, TextWrittenEvent)
        assert (event.object_id, event.key, event.before, event.after) == (_WELL, _NOTE.key, NothingWritten(), written)

    def test_write_text_on_other_kind_is_refused(self) -> None:
        """書いた文の鍵でない鍵に write_text を呼ぶと OperationNotForStateKindException を投げ、イベントはたまらない。"""
        state = _opened()

        with pytest.raises(OperationNotForStateKindException):
            state.write_text(_COVERED, TextBody("落書き"), _ALICE, _START)

        assert state.get_events() == []


class TestObjectStateReveal:
    """ObjectState.reveal が隠れていた物を現し、現れている物には何もしないことを保証する。"""

    def test_reveal_shows_hidden_object_and_records_event(self) -> None:
        """隠れている物を reveal すると is_revealed が True になり、物の ID を持つ ObjectRevealedEvent がたまる。"""
        state = _opened(_well(hidden=True))

        state.reveal()

        assert state.is_revealed()
        [event] = state.get_events()
        assert isinstance(event, ObjectRevealedEvent)
        assert event.object_id == _WELL

    def test_revealing_a_revealed_object_records_nothing(self) -> None:
        """現れている物を reveal しても断らず、イベントもたまらない。"""
        state = _opened(_well(hidden=False))

        state.reveal()

        assert state.get_events() == []
