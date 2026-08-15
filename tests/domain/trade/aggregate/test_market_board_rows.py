"""板をどう読むか — 表示のもとになる行を作る (経済統合 Phase 3)。

**読み出しは必ず「見る人」を引数に取る。** いまの検証シナリオ (5 人 3 職・
品目 4〜5 種) では、誰から見ても同じ行が出る。それでも引数の形を先に決めるのは、
品目が増えたときに「全件を見せて絞らせる」形が破綻するため。

旧マーケットボードのページ送り 11 ツールは、まさにこの問題への解だったが、
画面遷移で手番が溶ける形だったので不採用にした。将来の解は「一覧をやめて関心で
絞る」(自分の出品 / 自分の買い注文 / 自分の所持品 / 自分の職能で作れる品 /
買い注文が出ている品 の順で数行だけ出す) + 名前引きの検索ツール 1 つを想定
している。**見る人を引数に取らない実装にすると、そのとき全部書き直しになる。**

行の名前は**見る人の視点**で付ける。「売り最安 / 買い最高」ではなく
「自分が払う単価 (buy_price_gold) / 自分が受け取る単価 (sell_price_gold)」。
表示も「18G で買える / 15G で売れる」と、その人が次に打てる手の言葉で出す。
売り手視点と買い手視点が混線すると、同じ数字が誰にとっての値なのか読み違える。

見る人が今すでに効いている点も 2 つある。自分の注文は自分で受けられないので
**自分の注文を除いた値**が「その人に打てる手の値」であること。そして
引き取り待ちの行は他人には出さず、持ち主にだけ状態つきで見えること。
"""

from __future__ import annotations

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.market_board import MarketBoard
from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant

_LENA = MarketParticipant.player(PlayerId(1))
_TOM = MarketParticipant.player(PlayerId(2))
_BREAD = 7
_HERB = 8


def _order(order_id: int, **overrides) -> MarketOrder:
    kwargs = {
        "order_id": MarketOrderId(order_id),
        "side": MarketOrderSide.SELL,
        "owner": _LENA,
        "item_spec_id": _BREAD,
        "quantity": 1,
        "unit_price_gold": 18,
        "listed_at_tick": 5,
        "expires_in_ticks": 40,
    }
    kwargs.update(overrides)
    return MarketOrder.create(**kwargs)


def _board(*orders: MarketOrder) -> MarketBoard:
    board = MarketBoard.empty()
    for order in orders:
        board = board.with_order(order)
    return board


class TestTheRowsSummariseEachItem:
    """行は品目ごとにまとまる。"""

    def test_one_item_becomes_one_row(self) -> None:
        """同じ品目の注文が 3 件あっても、行は 1 つになる。"""
        board = _board(
            _order(1, unit_price_gold=18),
            _order(2, unit_price_gold=20),
            _order(3, unit_price_gold=25),
        )

        view = board.rows_for(_TOM)

        assert len(view.rows) == 1
        assert view.rows[0].item_spec_id == _BREAD

    def test_different_items_become_different_rows(self) -> None:
        """品目が違えば行も分かれる。"""
        board = _board(_order(1), _order(2, item_spec_id=_HERB))

        assert len(board.rows_for(_TOM).rows) == 2

    def test_the_row_counts_the_listings_and_the_goods(self) -> None:
        """行は、買える出品の件数と買える総数を持つ。

        件数だけだと「3 件あるが全部 1 つずつ」と「3 件で計 9 つ」が同じに
        見える。買える総量は別に要る。件数は競争の激しさ (4 件も出ている =
        下げないと売れない) を読む材料にもなる。
        """
        board = _board(
            _order(1, quantity=2), _order(2, quantity=3), _order(3, quantity=4),
        )

        row = board.rows_for(_TOM).rows[0]

        assert row.listing_count == 3
        assert row.buyable_quantity == 9

    def test_the_row_shows_what_you_pay_and_what_you_receive(self) -> None:
        """行は、その人が払う単価と受け取る単価を持つ。

        板の**売り注文は、見る人にとっては「買える」**。向きを取り違えると値が
        反対側に出る。この 2 つが並ぶことで需給が見え、値が交差していれば
        「18G で買えて 20G で売れる」とそのまま**機会**として読める
        (engine は交差を潰さない)。
        """
        board = _board(
            _order(1, side=MarketOrderSide.SELL, unit_price_gold=20),
            _order(2, side=MarketOrderSide.SELL, unit_price_gold=18),
            _order(3, side=MarketOrderSide.BUY, owner=_TOM, unit_price_gold=12),
            _order(4, side=MarketOrderSide.BUY, owner=_TOM, unit_price_gold=15),
        )

        row = board.rows_for(MarketParticipant.merchant(9)).rows[0]

        assert row.buy_price_gold == 18
        assert row.sell_price_gold == 15

    def test_a_move_you_cannot_make_has_no_price(self) -> None:
        """買い注文が 1 件も無ければ「売れない」になる (値は 0 ではなく無い)。

        0 を入れると「0G で売れる」と読めてしまう。
        """
        board = _board(_order(1, side=MarketOrderSide.SELL))

        row = board.rows_for(_TOM).rows[0]

        assert row.sell_price_gold is None
        assert row.bid_count == 0

    def test_an_empty_board_has_no_rows(self) -> None:
        """注文が 1 件も無い板には行が出ない。"""
        assert MarketBoard.empty().rows_for(_TOM).rows == ()


class TestThePricesShownAreThePricesYouCanTake:
    """見える値は、その人が実際に打てる手の値になる。"""

    def test_your_own_order_is_not_counted_as_a_price_you_can_take(self) -> None:
        """自分の出品は「買える値」に数えない。

        自分の注文は自分で受けられないので、自分の 18G を「18G で買える」と
        見せると、**買えない値を相場として読む**ことになる。
        """
        board = _board(
            _order(1, owner=_LENA, unit_price_gold=18),
            _order(2, owner=_TOM, unit_price_gold=20),
        )

        assert board.rows_for(_LENA).rows[0].buy_price_gold == 20

    def test_someone_else_can_still_buy_at_that_price(self) -> None:
        """他人から見れば、その 18G で買えるまま (正の対照)。"""
        board = _board(
            _order(1, owner=_LENA, unit_price_gold=18),
            _order(2, owner=_TOM, unit_price_gold=20),
        )

        assert board.rows_for(_TOM).rows[0].buy_price_gold == 18

    def test_a_row_of_only_your_own_orders_has_no_takeable_price(self) -> None:
        """自分の注文しか無い品目は「買えない」になる。"""
        board = _board(_order(1, owner=_LENA, unit_price_gold=18))

        row = board.rows_for(_LENA).rows[0]

        assert row.buy_price_gold is None
        assert row.listing_count == 0


class TestYourOwnOrdersAreListedOneByOne:
    """自分の注文だけは 1 件ずつ見える。

    集約表示だけだと、値を変える・取り下げるときに**どの注文を指すのかを
    組み立てられない**。自分の注文は品目と値が見える形で個別に出す。
    """

    def test_your_orders_are_returned_individually(self) -> None:
        """自分の出している注文が、1 件ずつ返る。"""
        board = _board(
            _order(1, owner=_LENA, unit_price_gold=20),
            _order(2, owner=_TOM, unit_price_gold=18),
        )

        own = board.rows_for(_LENA).own_orders

        assert [o.order_id for o in own] == [MarketOrderId(1)]

    def test_other_peoples_orders_are_not_yours(self) -> None:
        """他人の注文は自分の欄に出ない (正の対照)。"""
        board = _board(_order(1, owner=_TOM))

        assert board.rows_for(_LENA).own_orders == ()

    def test_an_order_awaiting_collection_is_listed_for_its_owner(self) -> None:
        """引き取り待ちの注文は、持ち主の欄に状態つきで出る。

        期限切れの通知を 1 回見落とした時点で取り戻す手がかりが消えるのを
        防ぐ。
        """
        board = _board(_order(1, owner=_LENA)).awaiting_collection(MarketOrderId(1))

        (own,) = board.rows_for(_LENA).own_orders

        assert own.is_awaiting_collection is True

    def test_an_order_awaiting_collection_is_not_offered_to_others(self) -> None:
        """引き取り待ちの注文は、他人の行には数えない (買えないものを見せない)。"""
        board = _board(_order(1, owner=_LENA)).awaiting_collection(MarketOrderId(1))

        assert board.rows_for(_TOM).rows == ()
