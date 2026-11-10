from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    CountStateKind,
    FlagStateKind,
    FlagValue,
    NoRefill,
    NothingWritten,
    StateKind,
    StockStateKind,
    TextBody,
    WrittenText,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import (
    ChoiceDuplicatedException,
    NoChoicesDeclaredException,
    StockCapacityBelowOneException,
    StockRefillIntervalBelowOneException,
    TextBodyBlankException,
)
from ai_rpg_world.game_world.domain.exception.world_design_exception import BlankDeclaredNameException
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, Ticks, WorldTick


class TestChoiceName:
    """ChoiceName が、選択の状態の値として宣言した空でない名前だけを表すことを保証する。"""

    def test_name_keeps_the_declared_text(self) -> None:
        """宣言した名前をそのまま持つ。"""
        assert ChoiceName("up").value == "up"

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_name_raises_blank_declared_name_exception(self, raw: str) -> None:
        """空、または空白だけの名前は BlankDeclaredNameException を投げる。"""
        with pytest.raises(BlankDeclaredNameException):
            ChoiceName(raw)


class TestChoiceStateKind:
    """ChoiceStateKind が、重ならない 1 つ以上の名前の並びだけを選択肢に持つことを保証する。"""

    def test_choices_keep_the_declared_order(self) -> None:
        """宣言した選択肢を、宣言した順のまま持つ。"""
        kind = ChoiceStateKind(choices=(ChoiceName("up"), ChoiceName("middle"), ChoiceName("down")))

        assert kind.choices == (ChoiceName("up"), ChoiceName("middle"), ChoiceName("down"))

    def test_no_choices_raises_domain_exception(self) -> None:
        """選択肢が 1 つも無いと NoChoicesDeclaredException を投げる。"""
        with pytest.raises(NoChoicesDeclaredException):
            ChoiceStateKind(choices=())

    def test_duplicated_choice_raises_domain_exception(self) -> None:
        """同じ名前の選択肢が 2 つあると ChoiceDuplicatedException を投げる。"""
        with pytest.raises(ChoiceDuplicatedException):
            ChoiceStateKind(choices=(ChoiceName("up"), ChoiceName("down"), ChoiceName("up")))


class TestStockStateKind:
    """StockStateKind が、1 以上の上限と、1 tick 以上の回復の間隔か回復しない印だけを持つことを保証する。"""

    def test_refilling_stock_keeps_capacity_and_interval(self) -> None:
        """上限と回復の間隔をそのまま持つ。"""
        kind = StockStateKind(capacity=Count(5), refills_every=Ticks(10))

        assert (kind.capacity, kind.refills_every) == (Count(5), Ticks(10))

    def test_stock_without_refill_is_allowed(self) -> None:
        """回復しない在庫は refills_every に NoRefill を書いて作れる。"""
        kind = StockStateKind(capacity=Count(1), refills_every=NoRefill())

        assert kind.refills_every == NoRefill()

    def test_zero_capacity_raises_domain_exception(self) -> None:
        """上限が 0 の在庫は StockCapacityBelowOneException を投げる。"""
        with pytest.raises(StockCapacityBelowOneException):
            StockStateKind(capacity=Count(0), refills_every=NoRefill())

    def test_zero_refill_interval_raises_domain_exception(self) -> None:
        """回復の間隔が 0 tick の在庫は StockRefillIntervalBelowOneException を投げる。"""
        with pytest.raises(StockRefillIntervalBelowOneException):
            StockStateKind(capacity=Count(5), refills_every=Ticks(0))


class TestTextBody:
    """TextBody が、書かれた文の空でない本文だけを表すことを保証する。"""

    def test_body_keeps_the_written_text(self) -> None:
        """書かれた本文をそのまま持つ。"""
        assert TextBody("北の扉は罠").value == "北の扉は罠"

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_body_raises_domain_exception(self, raw: str) -> None:
        """空、または空白だけの本文は TextBodyBlankException を投げる。"""
        with pytest.raises(TextBodyBlankException):
            TextBody(raw)


class TestStateKindHoldsWrittenText:
    """状態の種類が、書いた文を持つ種類かを自分で答えることを保証する。"""

    def test_written_text_kind_holds_written_text(self) -> None:
        """WrittenTextStateKind は holds_written_text に真を答える。"""
        assert WrittenTextStateKind().holds_written_text()

    @pytest.mark.parametrize(
        "kind",
        [
            FlagStateKind(),
            CountStateKind(),
            ChoiceStateKind((ChoiceName("up"),)),
            StockStateKind(Count(1), NoRefill()),
        ],
    )
    def test_other_kinds_do_not_hold_written_text(self, kind: StateKind) -> None:
        """旗・数・選択・在庫の種類は holds_written_text に偽を答える。"""
        assert not kind.holds_written_text()


class TestStateKindHoldsCountOrStock:
    """状態の種類が、数を持つ種類か・在庫を持つ種類かを自分で答えることを保証する。"""

    def test_count_kind_holds_count_and_not_stock(self) -> None:
        """CountStateKind は holds_count に真、holds_stock に偽を答える。"""
        assert (CountStateKind().holds_count(), CountStateKind().holds_stock()) == (True, False)

    def test_stock_kind_holds_stock_and_not_count(self) -> None:
        """StockStateKind は holds_stock に真、holds_count に偽を答える。"""
        stock = StockStateKind(Count(1), NoRefill())

        assert (stock.holds_count(), stock.holds_stock()) == (False, True)

    @pytest.mark.parametrize(
        "kind",
        [FlagStateKind(), ChoiceStateKind((ChoiceName("up"),)), WrittenTextStateKind()],
    )
    def test_other_kinds_hold_neither_count_nor_stock(self, kind: StateKind) -> None:
        """旗・選択・書いた文の種類は holds_count にも holds_stock にも偽を答える。"""
        assert (kind.holds_count(), kind.holds_stock()) == (False, False)


class TestWrittenTextStateKindCanHold:
    """WrittenTextStateKind.can_hold が、set で受けない書いた文も、持っている値としては受けることを保証する。"""

    def test_holds_written_text_and_nothing_written_but_not_a_flag(self) -> None:
        """書いた文と「何も書いていない」は持てると答え、旗の値は持てないと答える。set で受けるのは「何も書いていない」だけ。"""
        kind = WrittenTextStateKind()
        written = WrittenText(body=TextBody("水は濁っている"), author=PersonId("alice"), written_at=WorldTick(2))

        assert kind.can_hold(written)
        assert kind.can_hold(NothingWritten())
        assert not kind.can_hold(FlagValue(raised=True))
        assert not kind.accepts(written)
