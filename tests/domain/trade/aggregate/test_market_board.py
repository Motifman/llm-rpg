"""市場の掲示板そのものの振る舞い (経済統合 Phase 3)。

板は**自動では約定しない**。売り 20G と買い 22G が並んでも engine は潰さず、
どちらも板に残る。理由は、手番の外で持ち物が変わると、エージェントから見て
「自分が知らないうちに世界が変わった」ことになるため。取引は必ず誰かの手番の
決定として起きる。

結果として値の交差した注文が板に残るが、これは欠陥ではなく**機会**として
見える (「買い 22G が出ている、自分の 20G を受ければ 2G 得だ」)。人間が trace を
読んだとき約定漏れのバグに見えるので、意図であることを doc と PR 本文にも書く。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.market_board import MarketBoard
from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.exception.trade_exception import (
    MarketBoardStateException,
)
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant

_LENA = MarketParticipant.player(PlayerId(1))
_TOM = MarketParticipant.player(PlayerId(2))
_GUSTAV = MarketParticipant.merchant(9)
_BREAD = 7


def _order(order_id: int, **overrides) -> MarketOrder:
    kwargs = {
        "order_id": MarketOrderId(order_id),
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


class TestOrdersGoOntoTheBoard:
    """注文を置く・取り下げる。"""

    def test_placing_an_order_puts_one_row_on_the_board(self) -> None:
        """注文を 1 件置くと、板の行が 1 件になる。"""
        board = MarketBoard.empty().with_order(_order(1))

        assert len(board.orders) == 1

    def test_two_orders_for_the_same_item_stay_as_two_rows(self) -> None:
        """同じ品目の売り注文が 2 件あると、値が違うので別々の行として残る。

        まとめてしまうと、どちらの値で買えるのかが決まらない。値の競争そのものが
        見えなくなる。
        """
        board = (
            MarketBoard.empty()
            .with_order(_order(1, owner=_LENA, unit_price_gold=20))
            .with_order(_order(2, owner=_TOM, unit_price_gold=18))
        )

        assert len(board.orders) == 2
        assert sorted(o.unit_price_gold for o in board.orders) == [18, 20]

    def test_the_same_order_id_cannot_be_placed_twice(self) -> None:
        """同じ注文 ID を二度置けない (払い出しが壊れていることの検知)。"""
        board = MarketBoard.empty().with_order(_order(1))

        with pytest.raises(MarketBoardStateException):
            board.with_order(_order(1))

    def test_cancelling_removes_the_row(self) -> None:
        """自分の注文を取り下げると、板から消える。"""
        board = MarketBoard.empty().with_order(_order(1))

        after = board.cancelled(MarketOrderId(1), by=_LENA)

        assert after.orders == ()

    def test_someone_elses_order_cannot_be_cancelled(self) -> None:
        """他人の注文は取り下げられない。"""
        board = MarketBoard.empty().with_order(_order(1, owner=_LENA))

        with pytest.raises(MarketBoardStateException):
            board.cancelled(MarketOrderId(1), by=_TOM)

    def test_cancelling_an_absent_order_is_refused(self) -> None:
        """板に無い注文は取り下げられない (既に売り切れた注文を指した場合)。"""
        board = MarketBoard.empty()

        with pytest.raises(MarketBoardStateException):
            board.cancelled(MarketOrderId(1), by=_LENA)

    def test_placing_an_order_leaves_the_previous_board_untouched(self) -> None:
        """注文を置いても、元の板は変わらない (不変オブジェクト)。"""
        board = MarketBoard.empty()

        board.with_order(_order(1))

        assert board.orders == ()


class TestTheBoardNeverMatchesOnItsOwn:
    """板は自動で約定しない。値が交差しても、engine は潰さない。"""

    def test_a_crossing_pair_stays_on_the_board(self) -> None:
        """売り 20G と買い 22G を並べても、どちらも残数のまま板に残る。

        **正の対照**。自動約定を足した瞬間にこのテストが落ちる。
        """
        board = (
            MarketBoard.empty()
            .with_order(
                _order(1, owner=_LENA, side=MarketOrderSide.SELL, unit_price_gold=20)
            )
            .with_order(
                _order(2, owner=_TOM, side=MarketOrderSide.BUY, unit_price_gold=22)
            )
        )

        assert len(board.orders) == 2
        assert all(order.quantity == 3 for order in board.orders)


class TestOnlySomeoneElseCanTakeAnOrder:
    """約定は、注文を出した本人以外が受けたときだけ起きる。"""

    def test_taking_an_order_reduces_it_and_reports_the_trade(self) -> None:
        """売り注文を 1 件受けると、残数が 1 減り、約定の記録が返る。"""
        board = MarketBoard.empty().with_order(_order(1, quantity=3))

        after, trade = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=12)

        assert after.find(MarketOrderId(1)).quantity == 2
        assert trade.quantity == 1
        assert trade.unit_price_gold == 18

    def test_a_fully_taken_order_leaves_the_board(self) -> None:
        """残数を全部受けると、その注文は板から消える。"""
        board = MarketBoard.empty().with_order(_order(1, quantity=2))

        after, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=2, at_tick=12)

        assert after.find(MarketOrderId(1)) is None

    def test_your_own_order_cannot_be_taken_by_yourself(self) -> None:
        """自分の注文は自分で受けられない。

        gold と品が自分の中で往復するだけなのに、板には「約定した」履歴が
        値として残る。価格の時系列に偽の値が混ざるので実害がある。
        """
        board = MarketBoard.empty().with_order(_order(1, owner=_LENA))

        with pytest.raises(MarketBoardStateException):
            board.taken(MarketOrderId(1), by=_LENA, quantity=1, at_tick=12)

    def test_taking_an_absent_order_is_refused(self) -> None:
        """板に無い注文は受けられない (先に売り切れていた場合)。"""
        with pytest.raises(MarketBoardStateException):
            MarketBoard.empty().taken(
                MarketOrderId(1), by=_TOM, quantity=1, at_tick=12
            )


class TestTheTradeRecordCarriesWhoMovedThePrice:
    """約定の記録は、価格の時系列を後から引くための一次データになる。"""

    def test_taking_a_sell_order_records_the_seller_as_the_resting_side(self) -> None:
        """売り注文を受けた約定は、売り手が板に出していた側として残る。

        `taker_side` を持つのは、**値を決めたのがどちらか**が読めるようにする
        ため。売り注文が受けられたなら値は売り手が付けた値。これが無いと
        時系列は引けても「誰が値を動かしたか」が読めない。
        """
        board = MarketBoard.empty().with_order(
            _order(1, owner=_LENA, side=MarketOrderSide.SELL)
        )

        _, trade = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=12)

        assert trade.seller == _LENA
        assert trade.buyer == _TOM
        assert trade.taker_side is MarketOrderSide.BUY

    def test_taking_a_buy_order_records_the_buyer_as_the_resting_side(self) -> None:
        """買い注文を受けた約定は、買い手が板に出していた側として残る。

        売り手と買い手が入れ替わる。方向を取り違えると gold と品が逆に動く。
        """
        board = MarketBoard.empty().with_order(
            _order(1, owner=_TOM, side=MarketOrderSide.BUY)
        )

        _, trade = board.taken(MarketOrderId(1), by=_LENA, quantity=1, at_tick=12)

        assert trade.seller == _LENA
        assert trade.buyer == _TOM
        assert trade.taker_side is MarketOrderSide.SELL

    def test_the_trade_keeps_the_tick_and_the_order_it_came_from(self) -> None:
        """約定は、起きた手番と受けられた注文 ID を持つ。"""
        board = MarketBoard.empty().with_order(_order(1))

        _, trade = board.taken(MarketOrderId(1), by=_TOM, quantity=2, at_tick=12)

        assert trade.at_tick == 12
        assert trade.resting_order_id == MarketOrderId(1)
        assert trade.item_spec_id == _BREAD
        assert trade.total_gold == 36


class TestExpiryIsReadWithoutChangingTheBoard:
    """期限切れの取り出しは、板の状態を変えない。

    状態遷移と観測の発火は呼び出し側 (tick stage) の仕事にする。板が観測を
    持つと、保存・復元のたびに「流れた」が二重に届きうる (Phase 2 と同じ判断)。
    """

    def test_orders_past_their_expiry_are_listed(self) -> None:
        """期限を過ぎた注文が取り出せる。"""
        board = MarketBoard.empty().with_order(
            _order(1, listed_at_tick=5, expires_in_ticks=10)
        )

        assert [o.order_id for o in board.expired_orders(16)] == [MarketOrderId(1)]

    def test_live_orders_are_not_listed(self) -> None:
        """期限内の注文は取り出されない (正の対照)。"""
        board = MarketBoard.empty().with_order(
            _order(1, listed_at_tick=5, expires_in_ticks=10)
        )

        assert board.expired_orders(15) == ()

    def test_an_order_awaiting_collection_is_not_listed_again(self) -> None:
        """引き取り待ちにした注文は、二度と期限切れとして返らない。

        毎手番「流れた」が届き続けると、持ち主の観測が埋まる。
        """
        board = MarketBoard.empty().with_order(
            _order(1, listed_at_tick=5, expires_in_ticks=10)
        )
        board = board.awaiting_collection(MarketOrderId(1))

        assert board.expired_orders(16) == ()


class TestWhatEachViewerSeesOnTheBoard:
    """板の見え方は、見る人によって変わる。

    引き取り待ちの行は他人には買えないので見せない。ただし**持ち主には見える**。
    見えないと、観測が流れた 1 回きりの通知を見落とした時点で取り戻す手がかりが
    消える (静かな失敗)。
    """

    def test_a_live_order_is_visible_to_everyone(self) -> None:
        """生きている注文は、誰から見ても板に出ている。"""
        board = MarketBoard.empty().with_order(_order(1, owner=_LENA))

        assert len(board.orders_visible_to(_TOM)) == 1
        assert len(board.orders_visible_to(_LENA)) == 1

    def test_an_order_awaiting_collection_is_hidden_from_others(self) -> None:
        """引き取り待ちの行は、他人からは見えない (買えないものを見せない)。"""
        board = MarketBoard.empty().with_order(_order(1, owner=_LENA))
        board = board.awaiting_collection(MarketOrderId(1))

        assert board.orders_visible_to(_TOM) == ()

    def test_an_order_awaiting_collection_is_still_visible_to_its_owner(self) -> None:
        """引き取り待ちの行は、持ち主からは見える。

        空きを作って market_cancel で引き取る必要があるのに、板から自分の
        預け物が見えないと、取り戻す手がかりが消える。
        """
        board = MarketBoard.empty().with_order(_order(1, owner=_LENA))
        board = board.awaiting_collection(MarketOrderId(1))

        visible = board.orders_visible_to(_LENA)

        assert len(visible) == 1
        assert visible[0].is_awaiting_collection is True

    def test_a_merchant_order_is_visible_like_any_other(self) -> None:
        """商人の注文も、エージェントの注文と同じように板に並ぶ。"""
        board = MarketBoard.empty().with_order(_order(1, owner=_GUSTAV))

        assert len(board.orders_visible_to(_LENA)) == 1
