"""市場の板に出す注文 1 件の不変条件 (経済統合 Phase 3)。

板の注文は**単価で書く**。「パン 3 個で 10G」のような割り切れない束を許すと、
単価が小数になって価格の時系列が汚れ、エージェントが値を比べるときの見え方も
悪くなる。「パン 2 個で 30G」は単価 15G × 2 で書けるので表現力は落ちない。

注文は不変オブジェクトとして扱う。部分約定で残数が減るのは**新しい注文を
返す**形にして、同じ注文が二度削られる事故を状態の書き換えではなく生成の
失敗として捕まえる (Phase 2 の PendingTradeOffer と同じ判断)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.exception.trade_exception import (
    MarketOrderStateException,
    MarketOrderValidationException,
)
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_LENA = MarketParticipant.player(PlayerId(1))
_BREAD = 7


def _order(**overrides) -> MarketOrder:
    kwargs = {
        "order_id": MarketOrderId(1),
        "side": MarketOrderSide.SELL,
        "owner": _LENA,
        "item_spec_id": _BREAD,
        "quantity": 3,
        "unit_price_gold": 18,
        "listed_at_tick": 5,
        "expires_in_ticks": 40,
    }
    kwargs.update(overrides)
    return MarketOrder.create(**kwargs)


class TestASellOrderCarriesWhatItPromises:
    """売り注文は、品目・数量・単価・出し手・向きを持つ。"""

    def test_it_keeps_every_field_it_was_created_with(self) -> None:
        """作った注文から、品目・数量・単価・出し手・向きがそのまま読める。"""
        order = _order()

        assert order.item_spec_id == _BREAD
        assert order.quantity == 3
        assert order.unit_price_gold == 18
        assert order.owner == _LENA
        assert order.side is MarketOrderSide.SELL

    def test_the_expiry_is_the_listing_tick_plus_the_window(self) -> None:
        """期限は「出した手番 + 宣言された手番数」になる。"""
        order = _order(listed_at_tick=5, expires_in_ticks=40)

        assert order.expires_at_tick == 45

    def test_the_total_gold_is_the_unit_price_times_the_quantity(self) -> None:
        """注文全体の金額は単価 × 数量になる (単価から掛け算で出す)。"""
        order = _order(quantity=3, unit_price_gold=18)

        assert order.total_gold == 54


class TestAnUnusableOrderCannotBeCreated:
    """成立しえない注文は、板に載る前に落とす。"""

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_a_non_positive_quantity_is_refused(self, quantity: int) -> None:
        """数量 0 以下の注文は作れない (受けても何も動かない注文を板に置かない)。"""
        with pytest.raises(MarketOrderValidationException):
            _order(quantity=quantity)

    @pytest.mark.parametrize("price", [0, -1])
    def test_a_non_positive_unit_price_is_refused(self, price: int) -> None:
        """単価 0 以下の注文は作れない。

        0G の売り注文は「ただで配る」に見えるが、実際には板を占める行が増える
        だけで、贈与は give_item の仕事。価格の時系列にも 0 が混ざる。
        """
        with pytest.raises(MarketOrderValidationException):
            _order(unit_price_gold=price)

    @pytest.mark.parametrize("field", ["quantity", "unit_price_gold"])
    def test_a_boolean_is_not_accepted_as_a_number(self, field: str) -> None:
        """真偽値は数として通さない。

        Python では `bool` が `int` の派生なので、素直に書くと `True` が 1 と
        して通る。「パンを True 個」という注文が板に載る。
        """
        with pytest.raises(MarketOrderValidationException):
            _order(**{field: True})

    @pytest.mark.parametrize("window", [0, -1])
    def test_a_non_positive_expiry_window_is_refused(self, window: int) -> None:
        """0 手番以下の期限は作れない (出した瞬間に切れる注文を作らない)。"""
        with pytest.raises(MarketOrderValidationException):
            _order(expires_in_ticks=window)


class TestPartialFillLeavesTheOriginalUntouched:
    """部分約定は、残数を減らした**新しい注文**を返す。"""

    def test_filling_part_of_an_order_returns_a_smaller_order(self) -> None:
        """3 件のうち 1 件が約定すると、残数 2 の注文が返る。"""
        order = _order(quantity=3)

        remaining = order.filled_by(1)

        assert remaining.quantity == 2

    def test_the_original_order_is_not_modified(self) -> None:
        """約定させても、元の注文の残数は変わらない (不変オブジェクト)。"""
        order = _order(quantity=3)

        order.filled_by(1)

        assert order.quantity == 3

    def test_filling_the_whole_order_leaves_nothing(self) -> None:
        """全数が約定した注文は、残数 0 として返る (板から外す判断は板の側)。"""
        order = _order(quantity=3)

        remaining = order.filled_by(3)

        assert remaining.quantity == 0
        assert remaining.is_exhausted is True

    def test_filling_more_than_remains_is_refused(self) -> None:
        """残数を超える数量では約定できない。

        超過を黙って切り詰めると、買った側は「3 つ買えた」と思っているのに
        2 つしか届かない。数え違いが観測と食い違う形で残る。
        """
        order = _order(quantity=2)

        with pytest.raises(MarketOrderStateException):
            order.filled_by(3)

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_filling_by_a_non_positive_quantity_is_refused(self, quantity: int) -> None:
        """0 以下の数量では約定できない。"""
        order = _order(quantity=2)

        with pytest.raises(MarketOrderStateException):
            order.filled_by(quantity)


class TestTheExpiryIsReadAgainstTheClock:
    """期限を過ぎているかは、その時点の手番と比べて決まる。"""

    def test_it_is_not_expired_on_the_exact_tick(self) -> None:
        """期限の手番ちょうどは、まだ生きている扱いになる。

        「40 手番置ける」と宣言した注文が 40 手番目に消えると、宣言と挙動が
        1 手番ずれる (Phase 2 の提案期限と同じ判断)。
        """
        order = _order(listed_at_tick=5, expires_in_ticks=40)

        assert order.is_expired_at(45) is False

    def test_it_is_expired_after_the_tick(self) -> None:
        """期限の手番を過ぎると、期限切れになる。"""
        order = _order(listed_at_tick=5, expires_in_ticks=40)

        assert order.is_expired_at(46) is True


class TestAnOrderCanWaitToBeCollected:
    """引き取り待ちは、注文の状態として持つ。

    期限が切れても持ち主の所持品が満杯だと預けたものを返せない。消すと静かな
    失敗になるので、板に「引き取り待ち」として残し、空きを作ってから
    `market_cancel` で引き取れるようにする。
    """

    def test_a_fresh_order_is_not_awaiting_collection(self) -> None:
        """出したばかりの注文は、引き取り待ちではない。"""
        assert _order().is_awaiting_collection is False

    def test_it_can_be_marked_as_awaiting_collection(self) -> None:
        """引き取り待ちにすると、その状態を持った新しい注文が返る。"""
        order = _order()

        waiting = order.awaiting_collection()

        assert waiting.is_awaiting_collection is True
        assert order.is_awaiting_collection is False

    def test_an_order_awaiting_collection_cannot_be_filled(self) -> None:
        """引き取り待ちの注文は約定できない (もう板の商品ではない)。"""
        waiting = _order().awaiting_collection()

        with pytest.raises(MarketOrderStateException):
            waiting.filled_by(1)
