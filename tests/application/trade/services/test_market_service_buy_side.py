"""板の買い注文を受けて売る (経済統合 Phase 3、PR 3 の土台)。

買う側の鏡像だが、**鏡像は 2 つに分かれる**。「求めたとおりにできない」理由が
両側にあるため。

| | 買う | 売る |
|---|---|---|
| 板が足りない | 買えるだけ買う | 売れるだけ売る |
| 自分が足りない | gold 不足 → **断る** | 持っている数 → 売れるだけ売る |

買いの「自分が足りない」だけ構えが違うのは、**所持金は自分で見えている自分の
状態**だから (design_decisions #117)。板の中身も自分の持ち物の数も、外から
見えている値との食い違いではない。

買い手が受け取れないときは**板の足元**に落とす。買い手の足元だと落ちる場所が
その人の居場所に依存し、探しに行く先が決まらない。板の前なら、買い注文を出した
場所そのもので、本人が戻る理由も既にある。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.trade.services.market_service import (
    MarketItemNotOwnedError,
    MarketNothingToSellError,
    MarketOnlyYourOwnBidError,
    MarketService,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from tests.support.overflow_sinks import IGNORE_OVERFLOW

_TOWN = Path(__file__).resolve().parents[4] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_MINA = PlayerId(3)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    for pid, name in (("tom", "トム"), ("mina", "ミナ")):
        raw["players"].append({
            "id": pid, "name": name, "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 300,
            "persona_prompt": f"あなたは{name}。",
        })
    raw["market"] = {"board_spot": "market_square"}
    # レナの初期金はシナリオの屋台向けで、板の値付けを試すには足りない。
    raw["players"][0]["initial_gold"] = 300
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


@pytest.fixture()
def market(town: Any) -> MarketService:
    return town._market_service


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _held(runtime: Any, player_id: PlayerId, label: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return sum(c for s, c in counts.items() if s.value == _spec_id(runtime, label))


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    grant_item_specs_to_inventory(
        player_id,
        tuple(ItemSpecId.create(_spec_id(runtime, label)) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _gold(runtime: Any, player_id: PlayerId) -> int:
    return runtime._player_status_repo.find_by_id(player_id).gold.value


def _bid(runtime: Any, buyer: PlayerId, *, quantity: int, price: int) -> Any:
    return runtime._market_service.place_buy_order(
        buyer, item_label=_HERB, quantity=quantity, unit_price=price,
        current_tick=runtime.current_tick(),
    )


class TestSellingTakesTheHighestBidFirst:
    """売る側は、高い買い注文から順に受ける。"""

    def test_a_single_bid_is_taken_at_its_price(self, town: Any, market: MarketService) -> None:
        """買い注文が 1 件なら、その値で売れる。"""
        _bid(town, _TOM, quantity=1, price=8)
        _give(town, _LENA, _HERB, 1)
        before = _gold(town, _LENA)

        result = market.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert result.sold_quantity == 1
        assert _gold(town, _LENA) == before + 8
        assert _held(town, _TOM, _HERB) == 1

    def test_the_highest_bid_is_taken_first(self, town: Any, market: MarketService) -> None:
        """15G と 12G が並んでいるとき、15G から売れる。

        買う側が安い方から買うのと鏡像で、**売る側は高い方が良い**。
        """
        low = _bid(town, _TOM, quantity=1, price=12)
        high = _bid(town, _MINA, quantity=1, price=15)
        _give(town, _LENA, _HERB, 1)

        market.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert market.board().find(high.order_id) is None
        assert market.board().find(low.order_id) is not None

    def test_it_crosses_two_bids(self, town: Any, market: MarketService) -> None:
        """1 件で足りなければ、次の買い注文へまたがる。"""
        _bid(town, _TOM, quantity=1, price=15)
        _bid(town, _MINA, quantity=2, price=12)
        _give(town, _LENA, _HERB, 3)
        before = _gold(town, _LENA)

        result = market.sell_best(
            _LENA, item_label=_HERB, quantity=3, current_tick=town.current_tick(),
        )

        assert result.sold_quantity == 3
        assert _gold(town, _LENA) == before + 15 + 12 * 2

    def test_each_fill_is_reported_separately(self, town: Any, market: MarketService) -> None:
        """またいだとき、約定は 1 件ずつ返る (単価が違う)。"""
        _bid(town, _TOM, quantity=1, price=15)
        _bid(town, _MINA, quantity=2, price=12)
        _give(town, _LENA, _HERB, 3)

        result = market.sell_best(
            _LENA, item_label=_HERB, quantity=3, current_tick=town.current_tick(),
        )

        assert [s.trade.unit_price_gold for s in result.settlements] == [15, 12]

    def test_your_own_bid_is_skipped(self, town: Any, market: MarketService) -> None:
        """自分の買い注文は飛ばして売る (自己約定の禁止)。"""
        mine = _bid(town, _LENA, quantity=1, price=15)
        theirs = _bid(town, _TOM, quantity=1, price=12)
        _give(town, _LENA, _HERB, 1)

        market.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert market.board().find(mine.order_id) is not None
        assert market.board().find(theirs.order_id) is None


class TestSellingWhatYouCanWhenEitherSideIsShort:
    """足りない側は 2 つある。どちらも「売れるだけ売る」。"""

    def test_a_short_board_takes_what_it_wants(self, town: Any, market: MarketService) -> None:
        """板が求めている数が少ないときは、その数だけ売れる。

        **買う側の鏡像**。板の中身は他人の手番で変わるので、あるだけ応じる。
        """
        _bid(town, _TOM, quantity=2, price=8)
        _give(town, _LENA, _HERB, 3)

        result = market.sell_best(
            _LENA, item_label=_HERB, quantity=3, current_tick=town.current_tick(),
        )

        assert result.sold_quantity == 2
        assert result.requested_quantity == 3

    def test_holding_less_than_you_offer_sells_what_you_hold(
        self, town: Any, market: MarketService
    ) -> None:
        """自分の持っている数が足りないときも、売れるだけ売る。"""
        _bid(town, _TOM, quantity=3, price=8)
        _give(town, _LENA, _HERB, 1)

        result = market.sell_best(
            _LENA, item_label=_HERB, quantity=3, current_tick=town.current_tick(),
        )

        assert result.sold_quantity == 1
        assert result.requested_quantity == 3

    def test_holding_none_is_refused(self, town: Any, market: MarketService) -> None:
        """1 つも持っていない品は売れない。

        「売れるだけ売る」が 0 個になると、何も起きないのに成功と返ることに
        なる。持っていないなら、そう言って断る。
        """
        _bid(town, _TOM, quantity=1, price=8)

        with pytest.raises(MarketItemNotOwnedError):
            market.sell_best(
                _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
            )

    def test_an_item_nobody_wants_cannot_be_sold(self, town: Any, market: MarketService) -> None:
        """買い注文の無い品は売れない。"""
        _give(town, _LENA, _HERB, 1)

        with pytest.raises(MarketNothingToSellError):
            market.sell_best(
                _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
            )

    def test_only_your_own_bid_says_so(self, town: Any, market: MarketService) -> None:
        """自分の買い注文しか無い品は、別の失敗になる。

        次の一手が違う。誰も求めていないなら待つしかないが、自分が出している
        なら値を上げる手がある。
        """
        _bid(town, _LENA, quantity=1, price=8)
        _give(town, _LENA, _HERB, 1)

        with pytest.raises(MarketOnlyYourOwnBidError):
            market.sell_best(
                _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
            )

    def test_a_refused_sale_costs_nothing(self, town: Any, market: MarketService) -> None:
        """断られたとき、品も gold も動かない (正の対照)。"""
        _give(town, _LENA, _HERB, 1)
        held, gold = _held(town, _LENA, _HERB), _gold(town, _LENA)

        with pytest.raises(MarketNothingToSellError):
            market.sell_best(
                _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
            )

        assert _held(town, _LENA, _HERB) == held
        assert _gold(town, _LENA) == gold


class TestRepricingAndCancellingWorkOnBids:
    """値の付け直しと取り下げは、買い注文にも効く。"""

    def test_raising_a_bid_takes_more_gold(self, town: Any, market: MarketService) -> None:
        """買い注文の値を上げると、差額が預けられる。

        **売り注文と違って gold が動く。** 売り注文の「品も gold も動かない
        ので満杯でも打てる」は、売り注文側の事情から来ている。
        """
        _bid(town, _TOM, quantity=2, price=8)
        before = _gold(town, _TOM)

        market.reprice_order(
            _TOM, item_label=_HERB, side=MarketOrderSide.BUY, new_unit_price=10,
        )

        assert _gold(town, _TOM) == before - (10 - 8) * 2

    def test_lowering_a_bid_returns_gold(self, town: Any, market: MarketService) -> None:
        """値を下げると、余った gold が戻る。"""
        _bid(town, _TOM, quantity=2, price=10)
        before = _gold(town, _TOM)

        market.reprice_order(
            _TOM, item_label=_HERB, side=MarketOrderSide.BUY, new_unit_price=8,
        )

        assert _gold(town, _TOM) == before + (10 - 8) * 2

    def test_you_cannot_raise_a_bid_you_cannot_fund(
        self, town: Any, market: MarketService
    ) -> None:
        """払えない額へは上げられない (**自分の誤りには従わない**)。"""
        from ai_rpg_world.application.trade.services.market_service import (
            MarketGoldNotEnoughError,
        )

        _bid(town, _TOM, quantity=1, price=8)

        with pytest.raises(MarketGoldNotEnoughError):
            market.reprice_order(
                _TOM, item_label=_HERB, side=MarketOrderSide.BUY, new_unit_price=9999,
            )

    def test_cancelling_a_bid_returns_the_gold(self, town: Any, market: MarketService) -> None:
        """買い注文を取り下げると、預けた gold が戻る。"""
        before = _gold(town, _TOM)
        _bid(town, _TOM, quantity=2, price=8)

        market.cancel_by(_TOM, item_label=_HERB, side=MarketOrderSide.BUY)

        assert _gold(town, _TOM) == before

    def test_the_side_picks_the_right_order(self, town: Any, market: MarketService) -> None:
        """同じ品目に売りと買いがあるとき、向きで正しく選ばれる。

        取り違えると**別の注文を消す**。値だけ見ていると気づけない。
        """
        _give(town, _LENA, _HERB, 1)
        sell_order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=20,
            current_tick=town.current_tick(),
        )
        buy_order = _bid(town, _LENA, quantity=1, price=5)

        market.cancel_by(_LENA, item_label=_HERB, side=MarketOrderSide.BUY)

        assert market.board().find(sell_order.order_id) is not None
        assert market.board().find(buy_order.order_id) is None
