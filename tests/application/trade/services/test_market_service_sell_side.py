"""板から買う・値を付け直す・品名で取り下げる (経済統合 Phase 3、PR 2 の土台)。

エージェントは注文を選ばない。**品と数だけを指定し、安い方から順に買う**。
実際の取引所と同じ形で、表示が「18G で買える (出品 3件)」と集約されている
こととも噛み合う (どの注文を指すかを表示から組み立てられないため)。

在庫不足と gold 不足で構えを分ける。**外部の変化には適応し、自分の誤りには
従わない**: 板の中身は他人の手番で変わるので「あるだけ買う」。所持金は自分で
見える自分の状態なので、足りない買い注文は自分の計算違いであり、黙って数を
減らして成立させない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.trade.services.market_service import (
    MarketBoardNotHereError,
    MarketGoldNotEnoughError,
    MarketNoSuchOrderError,
    MarketNothingToBuyError,
    MarketOnlyYourOwnListingError,
    MarketService,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide

_TOWN = Path(__file__).resolve().parents[4] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_MINA = PlayerId(3)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    """板のある市場町。3 人が広場に居る。"""
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    for pid, name in (("tom", "トム"), ("mina", "ミナ")):
        raw["players"].append({
            "id": pid, "name": name, "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 200,
            "persona_prompt": f"あなたは{name}。",
        })
    raw["market"] = {"board_spot": "market_square"}
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


def _list_bread(
    runtime: Any, seller: PlayerId, *, quantity: int, price: int,
) -> Any:
    _give(runtime, seller, _BREAD, quantity)
    return runtime._market_service.place_sell_order(
        seller, item_label=_BREAD, quantity=quantity, unit_price=price,
        current_tick=runtime.current_tick(),
    )


class TestBuyingSweepsTheCheapestFirst:
    """買う側は注文を選ばない。安い方から順に買う。"""

    def test_a_single_listing_is_bought_at_its_price(
        self, town: Any, market: MarketService
    ) -> None:
        """出品が 1 件なら、その値で買える。"""
        _list_bread(town, _LENA, quantity=1, price=18)
        before = _gold(town, _TOM)

        result = market.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        assert result.bought_quantity == 1
        assert _held(town, _TOM, _BREAD) == 1
        assert _gold(town, _TOM) == before - 18

    def test_it_crosses_two_listings_when_one_is_not_enough(
        self, town: Any, market: MarketService
    ) -> None:
        """18G に 1 つ、20G に 2 つ出ているとき、3 つ買うと両方から買える。"""
        _list_bread(town, _LENA, quantity=1, price=18)
        _list_bread(town, _MINA, quantity=2, price=20)
        before = _gold(town, _TOM)

        result = market.buy_best(
            _TOM, item_label=_BREAD, quantity=3, current_tick=town.current_tick(),
        )

        assert result.bought_quantity == 3
        assert _gold(town, _TOM) == before - (18 + 20 * 2)

    def test_the_cheaper_listing_is_emptied_first(
        self, town: Any, market: MarketService
    ) -> None:
        """安い方から減る。1 つだけ買うと 18G の側が消える。"""
        cheap = _list_bread(town, _LENA, quantity=1, price=18)
        dear = _list_bread(town, _MINA, quantity=1, price=20)

        market.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        assert market.board().find(cheap.order_id) is None
        assert market.board().find(dear.order_id) is not None

    def test_your_own_listing_is_skipped(
        self, town: Any, market: MarketService
    ) -> None:
        """自分の出品は飛ばして買う。

        自己約定の禁止がここで効く。飛ばさないと、自分の 18G を自分で買って
        価格の時系列に偽の値が混ざる。
        """
        mine = _list_bread(town, _TOM, quantity=1, price=18)
        theirs = _list_bread(town, _LENA, quantity=1, price=20)
        before = _gold(town, _TOM)

        result = market.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        assert result.bought_quantity == 1
        assert _gold(town, _TOM) == before - 20
        assert market.board().find(mine.order_id) is not None
        assert market.board().find(theirs.order_id) is None

    def test_each_fill_is_reported_separately(
        self, town: Any, market: MarketService
    ) -> None:
        """またいで買うと、約定は 1 件ずつ返る。

        単価が違うので 1 件にまとめると価格の時系列が壊れる。trace も観測も
        ここから作る。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _list_bread(town, _MINA, quantity=2, price=20)

        result = market.buy_best(
            _TOM, item_label=_BREAD, quantity=3, current_tick=town.current_tick(),
        )

        assert [s.trade.unit_price_gold for s in result.settlements] == [18, 20]
        assert [s.trade.quantity for s in result.settlements] == [1, 2]


class TestWhatHappensWhenYouCannotHaveItAll:
    """外部の変化には適応し、自分の誤りには従わない。"""

    def test_a_short_board_sells_what_it_has(
        self, town: Any, market: MarketService
    ) -> None:
        """板の在庫が足りないときは、買えるだけ買う。

        板の中身は他人の手番で変わるので、「あるだけ買う」が自然。
        """
        _list_bread(town, _LENA, quantity=2, price=18)

        result = market.buy_best(
            _TOM, item_label=_BREAD, quantity=3, current_tick=town.current_tick(),
        )

        assert result.bought_quantity == 2

    def test_the_result_keeps_both_the_wish_and_the_outcome(
        self, town: Any, market: MarketService
    ) -> None:
        """買えるだけ買ったとき、求めた数と買えた数の両方が残る。

        買えた数だけだと、読む側は自分の意図が満たされたか判断できない。
        """
        _list_bread(town, _LENA, quantity=2, price=18)

        result = market.buy_best(
            _TOM, item_label=_BREAD, quantity=3, current_tick=town.current_tick(),
        )

        assert result.requested_quantity == 3
        assert result.bought_quantity == 2

    def test_a_purse_that_is_too_light_buys_nothing(
        self, town: Any, market: MarketService
    ) -> None:
        """gold が足りないときは、1 つも買わずに断る。

        所持金は**自分で見える自分の状態**なので、足りないのは自分の計算違い。
        黙って数を減らすと、意図と違う買い物が成立する。
        """
        _list_bread(town, _LENA, quantity=3, price=100)
        before = _gold(town, _TOM)

        with pytest.raises(MarketGoldNotEnoughError):
            market.buy_best(
                _TOM, item_label=_BREAD, quantity=3, current_tick=town.current_tick(),
            )

        assert _gold(town, _TOM) == before
        assert _held(town, _TOM, _BREAD) == 0

    def test_an_item_nobody_listed_cannot_be_bought(
        self, town: Any, market: MarketService
    ) -> None:
        """誰も出していない品は買えない。"""
        with pytest.raises(MarketNothingToBuyError):
            market.buy_best(
                _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
            )

    def test_an_item_only_you_listed_says_so(
        self, town: Any, market: MarketService
    ) -> None:
        """自分の出品しか無い品は、「誰も出していない」とは別の失敗になる。

        次の一手が違う。誰も出していないなら待つしかないが、自分が出している
        なら値を下げる手がある。
        """
        _list_bread(town, _TOM, quantity=1, price=18)

        with pytest.raises(MarketOnlyYourOwnListingError):
            market.buy_best(
                _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
            )


class TestRepricingMovesThePriceWithoutMovingTheGoods:
    """値の付け直しは、品を動かさずに値だけ変える。"""

    def test_the_price_changes(self, town: Any, market: MarketService) -> None:
        """自分の売り注文の単価を変えられる。"""
        order = _list_bread(town, _LENA, quantity=2, price=20)

        after = market.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        assert after.unit_price_gold == 18
        assert market.board().find(order.order_id).unit_price_gold == 18

    def test_it_works_with_a_full_inventory(
        self, town: Any, market: MarketService
    ) -> None:
        """所持品が満杯でも値を変えられる。

        **これが値の付け直しを入れた理由**。取り下げは預けた品を引き取るので
        満杯だと断られ、「1 件まで」の制限と合わさって**値を変えられない**
        詰まりが生まれていた。値下げはこの実験でいちばん見たい行動なので、
        品を動かさずに打てる手が要る。
        """
        _list_bread(town, _LENA, quantity=1, price=20)
        while not town._player_inventory_repo.find_by_id(_LENA).is_inventory_full():
            _give(town, _LENA, _HERB, 1)

        after = market.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        assert after.unit_price_gold == 18

    def test_the_goods_do_not_move(self, town: Any, market: MarketService) -> None:
        """値を変えても、預けた品は板に残ったまま (正の対照)。"""
        _list_bread(town, _LENA, quantity=2, price=20)
        held = _held(town, _LENA, _BREAD)

        market.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        assert _held(town, _LENA, _BREAD) == held
        assert market.board().orders[0].quantity == 2

    def test_the_expiry_does_not_move(self, town: Any, market: MarketService) -> None:
        """値を変えても期限は伸びない。

        伸びると、値下げが**期限の延命に使える**。板に居座り続ける注文を
        作れてしまい、期限機構が骨抜きになる。
        """
        order = _list_bread(town, _LENA, quantity=1, price=20)

        after = market.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        assert after.expires_at_tick == order.expires_at_tick

    def test_someone_elses_order_cannot_be_repriced(
        self, town: Any, market: MarketService
    ) -> None:
        """他人の注文の値は変えられない。"""
        _list_bread(town, _LENA, quantity=1, price=20)

        with pytest.raises(MarketNoSuchOrderError):
            market.reprice_order(
                _TOM, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
            )

    def test_an_order_awaiting_collection_cannot_be_repriced(
        self, town: Any, market: MarketService
    ) -> None:
        """引き取り待ちの注文は値を変えられない (もう板の商品ではない)。"""
        order = _list_bread(town, _LENA, quantity=1, price=20)
        while not town._player_inventory_repo.find_by_id(_LENA).is_inventory_full():
            _give(town, _LENA, _HERB, 1)
        market.expire_orders(current_tick=order.expires_at_tick + 1)

        with pytest.raises(MarketNoSuchOrderError):
            market.reprice_order(
                _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
            )


class TestYourOwnOrderIsNamedByItsItemAndSide:
    """自分の注文は、品名と向きで指す。

    「1 件まで」の制限があるので一意に決まる。番号で指す形は「表示に出ている
    名前をそのまま渡す」規約から外れる。
    """

    def test_cancelling_by_item_and_side_works(
        self, town: Any, market: MarketService
    ) -> None:
        """品名と向きで、自分の注文を取り下げられる。"""
        _list_bread(town, _LENA, quantity=2, price=20)

        market.cancel_by(_LENA, item_label=_BREAD, side=MarketOrderSide.SELL)

        assert market.board().orders == ()
        assert _held(town, _LENA, _BREAD) == 2

    def test_cancelling_what_you_never_listed_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """出していない品は取り下げられない。"""
        with pytest.raises(MarketNoSuchOrderError):
            market.cancel_by(_LENA, item_label=_BREAD, side=MarketOrderSide.SELL)

    def test_someone_elses_order_is_not_yours_to_cancel(
        self, town: Any, market: MarketService
    ) -> None:
        """他人が同じ品を出していても、自分の注文としては見つからない。"""
        _list_bread(town, _LENA, quantity=1, price=20)

        with pytest.raises(MarketNoSuchOrderError):
            market.cancel_by(_TOM, item_label=_BREAD, side=MarketOrderSide.SELL)


class TestTheBoardHasToBeWithinReach:
    """板と同席していないと、板は使えない。

    露出では見ない (ツール自体は出したままにする)。出したり消したりすると、
    エージェントから見て世界の可能性が揺れる。同席は実行時の失敗にする
    (商人の `MERCHANT_NOT_AT_SPOT` と同じ形)。
    """

    def test_listing_from_afar_is_refused(self, town: Any, market: MarketService) -> None:
        """板から離れた場所では出品できない。"""
        _give(town, _LENA, _BREAD, 1)
        _walk_away(town, _LENA)

        with pytest.raises(MarketBoardNotHereError):
            market.place_sell_order(
                _LENA, item_label=_BREAD, quantity=1, unit_price=18,
                current_tick=town.current_tick(),
            )

    def test_buying_from_afar_is_refused(self, town: Any, market: MarketService) -> None:
        """板から離れた場所では買えない。"""
        _list_bread(town, _LENA, quantity=1, price=18)
        _walk_away(town, _TOM)

        with pytest.raises(MarketBoardNotHereError):
            market.buy_best(
                _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
            )

    def test_being_at_the_board_is_enough(self, town: Any, market: MarketService) -> None:
        """板と同席していれば使える (正の対照)。

        同席の判定が常に False になる壊れ方を見逃さない。
        """
        _give(town, _LENA, _BREAD, 1)

        order = market.place_sell_order(
            _LENA, item_label=_BREAD, quantity=1, unit_price=18,
            current_tick=town.current_tick(),
        )

        assert market.board().find(order.order_id) is not None


def _walk_away(runtime: Any, player_id: PlayerId) -> None:
    """板の無いスポットへ移す。"""
    from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

    graph = runtime._spot_graph_repo.find_graph()
    here = graph.get_entity_spot(EntityId.create(int(player_id)))
    elsewhere = next(
        spot for spot in graph.neighbor_spot_ids_for_routing(here) if spot != here
    )
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(EntityId.create(int(player_id)), elsewhere)
    runtime._spot_graph_repo.save(graph)
