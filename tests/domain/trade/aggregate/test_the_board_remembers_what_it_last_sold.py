"""板が「その品が直近いくらで成立したか」を憶えている (経済統合 Phase 3)。

**値付けの手がかりのうち、板の内側から出せる唯一のものが約定価格**。最良の
売り値・買い値は「誰かが望んでいる値」でしかなく、その値で成立するとは限ら
ない。実 run で値付けを動かした唯一の実例は t71 の「商人が 10G で売ってるから
9G にしておけばすぐ売れる」で、**外から与えられた参照価格**が効いていた。板の
約定価格は同じ役割を板の内側で果たす。

**憶える場所を板そのものにする。** 約定を作れるのは ``taken`` だけで、そこが
同時に新しい板を返す。service 側で「約定したら記録する」形にすると、約定の
経路が増えたときに片方だけ記録し忘れる (`buy_best` / `sell_best` / `take_order`
の 3 経路がある)。板に持たせれば、記録し忘れた板を作る道が無い。

trace ではなく世界の状態として持つ。trace は分析用の出力で、世界の中の誰も
読めない。板を引くツールから読める必要がある。
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


def _row(board: MarketBoard, item_spec_id: int, viewer=_TOM):
    for row in board.rows_for(viewer).rows:
        if row.item_spec_id == item_spec_id:
            return row
    return None


class TestTheBoardRecordsThePriceThatActuallyCleared:
    """約定するとその品目の直近の約定価格が板に残り、行から読める。"""

    def test_a_settled_order_leaves_its_unit_price_on_the_row(self) -> None:
        """1 件が約定すると、その品目の行に約定した単価が出る。"""
        board = _board(_order(1, unit_price_gold=18))

        board, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=9)

        assert board.last_trade_price_of(_BREAD) == 18

    def test_an_item_that_never_traded_has_no_price(self) -> None:
        """一度も約定していない品目の直近の約定価格は None になる。

        0 を返すと「0G で成立した」と読める。**無いことは無いと言う。**
        """
        board = _board(_order(1, item_spec_id=_HERB))

        assert board.last_trade_price_of(_HERB) is None

    def test_the_row_carries_the_last_traded_price(self) -> None:
        """行に直近の約定価格が載り、板を 1 回引けば値付けの材料が揃う。"""
        board = _board(_order(1, unit_price_gold=18), _order(2, unit_price_gold=22))
        board, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=9)

        row = _row(board, _BREAD)

        assert row is not None
        assert row.last_trade_price_gold == 18
        assert row.buy_price_gold == 22

    def test_a_later_trade_replaces_the_earlier_one(self) -> None:
        """同じ品目で二度目が約定すると、直近の約定価格は新しい方になる。"""
        board = _board(_order(1, unit_price_gold=18), _order(2, unit_price_gold=22))
        board, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=9)

        board, _ = board.taken(MarketOrderId(2), by=_TOM, quantity=1, at_tick=11)

        assert board.last_trade_price_of(_BREAD) == 22

    def test_each_item_keeps_its_own_price(self) -> None:
        """品目ごとに別々に憶える。他の品が約定しても値は移らない。"""
        board = _board(
            _order(1, unit_price_gold=18),
            _order(2, item_spec_id=_HERB, unit_price_gold=5),
        )
        board, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=9)
        board, _ = board.taken(MarketOrderId(2), by=_TOM, quantity=1, at_tick=10)

        assert board.last_trade_price_of(_BREAD) == 18
        assert board.last_trade_price_of(_HERB) == 5

    def test_a_partial_fill_across_two_orders_keeps_the_last_one(self) -> None:
        """安い方から順に 2 件をまたいで買うと、直近の約定は最後の 1 件になる。

        平均や加重平均は採らない。**約定は単価ごとに 1 件として扱う**という
        判断が既にあり (trace も約定ごとに 1 行で、平均を出さないと決めた)、
        そこへ揃える。平均を混ぜると、値の時系列に一度も成立しなかった値が
        入る。
        """
        board = _board(_order(1, unit_price_gold=18), _order(2, unit_price_gold=22))

        board, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=9)
        board, _ = board.taken(MarketOrderId(2), by=_TOM, quantity=1, at_tick=9)

        assert board.last_trade_price_of(_BREAD) == 22


class TestThePriceSurvivesEveryOtherChangeToTheBoard:
    """板を変えるどの操作を通っても、憶えた約定価格は消えない。

    板を変えるメソッドは新しい ``MarketBoard`` を作って返す。そこで
    ``orders`` だけを渡す書き方をすると、約定価格が**黙って落ちる**。落ちても
    例外は出ず、板を引いたときに欄が消えるだけなので気付けない。
    """

    def _traded(self) -> MarketBoard:
        board = _board(_order(1, unit_price_gold=18))
        board, _ = board.taken(MarketOrderId(1), by=_TOM, quantity=1, at_tick=9)
        return board

    def test_placing_another_order_keeps_it(self) -> None:
        """新しい注文を置いても直近の約定価格は残る。"""
        board = self._traded().with_order(_order(2, unit_price_gold=25))

        assert board.last_trade_price_of(_BREAD) == 18

    def test_cancelling_an_order_keeps_it(self) -> None:
        """注文を取り下げても直近の約定価格は残る。"""
        board = self._traded().with_order(_order(2))

        board = board.cancelled(MarketOrderId(2), by=_LENA)

        assert board.last_trade_price_of(_BREAD) == 18

    def test_repricing_an_order_keeps_it(self) -> None:
        """値を変えても直近の約定価格は残る。"""
        board = self._traded().with_order(_order(2, unit_price_gold=25))

        board = board.with_repriced(board.find(MarketOrderId(2)).repriced(30))

        assert board.last_trade_price_of(_BREAD) == 18

    def test_moving_an_order_to_awaiting_collection_keeps_it(self) -> None:
        """引き取り待ちにしても直近の約定価格は残る。"""
        board = self._traded().with_order(_order(2))

        board = board.awaiting_collection(MarketOrderId(2))

        assert board.last_trade_price_of(_BREAD) == 18
