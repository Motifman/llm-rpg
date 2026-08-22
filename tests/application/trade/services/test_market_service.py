"""板に注文を出し、受け、取り下げ、期限で戻すところまで (経済統合 Phase 3)。

板は**預かる**。出品した品は所持品から消えて板に移り、買い注文を出したら
gold が残高から引かれて板に移る。Phase 2 の同席取引は凍結 (手元に残したまま
予約する) だったが、板は預ける方を選んだ。凍結だと所持品の表示と実際に使える
量がずれ、Phase 2 ではそこで二重減算のバグが生まれた。板に預ければ、所持品から
消えて板の行として見えるので、**物がどこにあるかが観測と一致する**。

商人は**世界の外との出入り口**なので、商人が買い取った品は世界から消え、
商人へ払った gold も世界から消える。Phase 1 で商人の gold を無限と決めたのと
同じ一本の理由から出ている。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.trade.services.market_service import (
    MarketDuplicateOrderError,
    MarketGoldNotEnoughError,
    MarketInventoryFullError,
    MarketItemNotOwnedError,
    MarketOrderAwaitingCollectionError,
    MarketService,
    MarketUnknownItemError,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant

_TOWN = Path(__file__).resolve().parents[4] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    """レナとトムの 2 人が居る市場町を作る。"""
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"].append({
        "id": "tom", "name": "トム",
        "spawn_spot": raw["players"][0]["spawn_spot"],
        "initial_items": [], "initial_gold": 100,
        "persona_prompt": "あなたはトム。",
    })
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


@pytest.fixture()
def market(town: Any) -> MarketService:
    return town._market_service


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _held(runtime: Any, player_id: PlayerId, label: str) -> int:
    """その人が持っている品の数。"""
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return sum(
        count
        for spec, count in counts.items()
        if spec.value == _spec_id(runtime, label)
    )


def _world_held(runtime: Any, label: str) -> int:
    """世界の中の誰かが持っている品の総数 (商人の吸収を数えるのに使う)。"""
    return sum(_held(runtime, PlayerId(pid), label) for pid in (1, 2))


def _gold(runtime: Any, player_id: PlayerId) -> int:
    return runtime._player_status_repo.find_by_id(player_id).gold.value


def _world_gold(runtime: Any) -> int:
    return sum(_gold(runtime, PlayerId(pid)) for pid in (1, 2))


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

    grant_item_specs_to_inventory(
        player_id,
        tuple(ItemSpecId.create(_spec_id(runtime, label)) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _fill_inventory(runtime: Any, player_id: PlayerId, label: str) -> None:
    """所持品を満杯にする。"""
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    while not inventory.is_inventory_full():
        _give(runtime, player_id, label, 1)
        inventory = runtime._player_inventory_repo.find_by_id(player_id)


class TestListingHandsTheGoodsToTheBoard:
    """出品すると、品は所持品から板へ移る。"""

    def test_the_item_leaves_the_inventory(self, town: Any, market: MarketService) -> None:
        """薬草を 1 つ出品すると、所持品から 1 つ減る。"""
        _give(town, _LENA, _HERB, 2)
        before = _held(town, _LENA, _HERB)

        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        assert _held(town, _LENA, _HERB) == before - 1

    def test_the_order_appears_on_the_board(self, town: Any, market: MarketService) -> None:
        """出品した注文が板に載る。"""
        _give(town, _LENA, _HERB, 1)

        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        assert market.board().find(order.order_id) is not None

    def test_an_item_you_do_not_hold_cannot_be_listed(
        self, town: Any, market: MarketService
    ) -> None:
        """持っていない品は出品できない。"""
        with pytest.raises(MarketItemNotOwnedError):
            market.place_sell_order(
                _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
            )

    def test_listing_more_than_you_hold_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """持っている数を超えては出品できない。"""
        _give(town, _LENA, _HERB, 1)

        with pytest.raises(MarketItemNotOwnedError):
            market.place_sell_order(
                _LENA, item_label=_HERB, quantity=2, unit_price=8, current_tick=1,
            )

    def test_an_unknown_item_name_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """この世界に無い品名では出品できない。"""
        with pytest.raises(MarketUnknownItemError):
            market.place_sell_order(
                _LENA, item_label="幻の果実", quantity=1, unit_price=8, current_tick=1,
            )


class TestBiddingHandsTheGoldToTheBoard:
    """買い注文を出すと、gold は残高から板へ移る。"""

    def test_the_gold_leaves_the_balance(self, town: Any, market: MarketService) -> None:
        """薬草 2 つを 1 つ 7G で求めると、残高から 14G 減る。"""
        before = _gold(town, _TOM)

        market.place_buy_order(
            _TOM, item_label=_HERB, quantity=2, unit_price=7, current_tick=1,
        )

        assert _gold(town, _TOM) == before - 14

    def test_a_bid_you_cannot_pay_for_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """払えない額の買い注文は出せない。"""
        with pytest.raises(MarketGoldNotEnoughError):
            market.place_buy_order(
                _TOM, item_label=_HERB, quantity=100, unit_price=999, current_tick=1,
            )

    def test_the_gold_is_not_spent_when_the_bid_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """買い注文が断られたとき、残高は 1G も減らない (正の対照)。"""
        before = _gold(town, _TOM)

        with pytest.raises(MarketGoldNotEnoughError):
            market.place_buy_order(
                _TOM, item_label=_HERB, quantity=100, unit_price=999, current_tick=1,
            )

        assert _gold(town, _TOM) == before


class TestTakingAnOrderMovesBothSides:
    """注文を受けると、品と gold が入れ替わる。"""

    def test_taking_a_sell_order_gives_goods_to_the_taker(
        self, town: Any, market: MarketService
    ) -> None:
        """売り注文を受けると、受けた側に品が渡る。"""
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.take_order(_TOM, order_id=order.order_id, quantity=1, current_tick=2)

        assert _held(town, _TOM, _HERB) == 1

    def test_taking_a_sell_order_pays_the_seller(
        self, town: Any, market: MarketService
    ) -> None:
        """売り注文を受けると、出品者に代金が入る。"""
        _give(town, _LENA, _HERB, 1)
        before = _gold(town, _LENA)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.take_order(_TOM, order_id=order.order_id, quantity=1, current_tick=2)

        assert _gold(town, _LENA) == before + 8

    def test_taking_a_buy_order_pays_the_seller_from_the_board(
        self, town: Any, market: MarketService
    ) -> None:
        """買い注文を受けると、板に預けられていた gold が売り手へ渡る。

        買い手の残高は注文を出した時点で既に引かれているので、ここでもう一度
        引くと二重に払うことになる (Phase 2 の二重減算と同じ形)。
        """
        order = market.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=7, current_tick=1,
        )
        _give(town, _LENA, _HERB, 1)
        tom_gold_after_bid = _gold(town, _TOM)
        lena_before = _gold(town, _LENA)

        market.take_order(_LENA, order_id=order.order_id, quantity=1, current_tick=2)

        assert _gold(town, _LENA) == lena_before + 7
        assert _gold(town, _TOM) == tom_gold_after_bid

    def test_taking_a_buy_order_delivers_the_goods(
        self, town: Any, market: MarketService
    ) -> None:
        """買い注文を受けると、品が買い手に渡る。"""
        order = market.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=7, current_tick=1,
        )
        _give(town, _LENA, _HERB, 1)

        market.take_order(_LENA, order_id=order.order_id, quantity=1, current_tick=2)

        assert _held(town, _TOM, _HERB) == 1
        assert _held(town, _LENA, _HERB) == 0

    def test_a_partial_fill_leaves_the_rest_on_the_board(
        self, town: Any, market: MarketService
    ) -> None:
        """3 件のうち 1 件だけ受けると、板に 2 件残り、受け渡しも 1 件ぶんになる。"""
        _give(town, _LENA, _HERB, 3)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=3, unit_price=8, current_tick=1,
        )

        market.take_order(_TOM, order_id=order.order_id, quantity=1, current_tick=2)

        assert market.board().find(order.order_id).quantity == 2
        assert _held(town, _TOM, _HERB) == 1

    def test_taking_more_than_you_can_pay_for_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """代金を払えないと売り注文は受けられない。"""
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=9999, current_tick=1,
        )

        with pytest.raises(MarketGoldNotEnoughError):
            market.take_order(
                _TOM, order_id=order.order_id, quantity=1, current_tick=2,
            )

    def test_taking_a_buy_order_without_the_goods_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """求められている品を持っていないと、買い注文は受けられない。"""
        order = market.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=7, current_tick=1,
        )

        with pytest.raises(MarketItemNotOwnedError):
            market.take_order(
                _LENA, order_id=order.order_id, quantity=1, current_tick=2,
            )

    def test_taking_with_a_full_inventory_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """受け取る空きが無いときは、約定させずに断る。

        `acquire_item` は満杯だと**黙って品を捨てる** (溢れイベントを出して
        return する)。代金だけ払って品が消えるのは、いちばん質の悪い静かな
        失敗になる。受ける前に空きを確かめる。
        """
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        _fill_inventory(town, _TOM, _HERB)

        with pytest.raises(MarketInventoryFullError):
            market.take_order(
                _TOM, order_id=order.order_id, quantity=1, current_tick=2,
            )

    def test_a_refused_take_costs_nothing(
        self, town: Any, market: MarketService
    ) -> None:
        """受けられなかったとき、gold も品も動かない (正の対照)。"""
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=9999, current_tick=1,
        )
        tom_gold = _gold(town, _TOM)
        lena_gold = _gold(town, _LENA)

        with pytest.raises(MarketGoldNotEnoughError):
            market.take_order(
                _TOM, order_id=order.order_id, quantity=1, current_tick=2,
            )

        assert _gold(town, _TOM) == tom_gold
        assert _gold(town, _LENA) == lena_gold
        assert market.board().find(order.order_id).quantity == 1


class TestCancellingReturnsWhatWasDeposited:
    """取り下げると、預けたものが持ち主へ戻る。"""

    def test_cancelling_a_sell_order_returns_the_goods(
        self, town: Any, market: MarketService
    ) -> None:
        """売り注文を取り下げると、預けた品が戻る。"""
        _give(town, _LENA, _HERB, 2)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=2, unit_price=8, current_tick=1,
        )

        market.cancel_order(_LENA, order_id=order.order_id)

        assert _held(town, _LENA, _HERB) == 2

    def test_cancelling_a_buy_order_returns_the_gold(
        self, town: Any, market: MarketService
    ) -> None:
        """買い注文を取り下げると、預けた gold が戻る。"""
        before = _gold(town, _TOM)
        order = market.place_buy_order(
            _TOM, item_label=_HERB, quantity=2, unit_price=7, current_tick=1,
        )

        market.cancel_order(_TOM, order_id=order.order_id)

        assert _gold(town, _TOM) == before

    def test_only_the_remaining_quantity_comes_back(
        self, town: Any, market: MarketService
    ) -> None:
        """一部が売れた後に取り下げると、残っていたぶんだけ戻る。"""
        _give(town, _LENA, _HERB, 3)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=3, unit_price=8, current_tick=1,
        )
        market.take_order(_TOM, order_id=order.order_id, quantity=1, current_tick=2)

        market.cancel_order(_LENA, order_id=order.order_id)

        assert _held(town, _LENA, _HERB) == 2


class TestExpiryReturnsWhatWasDeposited:
    """期限が切れると、預けたものが持ち主へ戻る。"""

    def test_an_expired_sell_order_returns_the_goods(
        self, town: Any, market: MarketService
    ) -> None:
        """期限切れの売り注文は、預けた品を持ち主へ返す。"""
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.expire_orders(current_tick=order.expires_at_tick + 1)

        assert _held(town, _LENA, _HERB) == 1
        assert market.board().find(order.order_id) is None

    def test_an_expired_buy_order_returns_the_gold(
        self, town: Any, market: MarketService
    ) -> None:
        """期限切れの買い注文は、預けた gold を持ち主へ返す。"""
        before = _gold(town, _TOM)
        order = market.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=7, current_tick=1,
        )

        market.expire_orders(current_tick=order.expires_at_tick + 1)

        assert _gold(town, _TOM) == before

    def test_a_live_order_is_left_alone(self, town: Any, market: MarketService) -> None:
        """期限内の注文は、そのまま板に残る (正の対照)。"""
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.expire_orders(current_tick=order.expires_at_tick)

        assert market.board().find(order.order_id) is not None

    def test_goods_that_cannot_be_returned_wait_on_the_board(
        self, town: Any, market: MarketService
    ) -> None:
        """所持品が満杯で返せない品は、板に「引き取り待ち」として残る。

        消すと静かな失敗になる。空きを作ってから market_cancel で引き取れる。
        """
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        _fill_inventory(town, _LENA, _HERB)

        market.expire_orders(current_tick=order.expires_at_tick + 1)

        waiting = market.board().find(order.order_id)
        assert waiting is not None
        assert waiting.is_awaiting_collection is True

    def test_an_order_awaiting_collection_does_not_expire_again(
        self, town: Any, market: MarketService
    ) -> None:
        """引き取り待ちの注文は、次の手番でもう一度期限切れにならない。"""
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        _fill_inventory(town, _LENA, _HERB)
        market.expire_orders(current_tick=order.expires_at_tick + 1)

        expired_again = market.expire_orders(current_tick=order.expires_at_tick + 2)

        assert expired_again == ()


def test_market_board_rollback_snapshot_restores_board_and_next_order_id(
    town: Any, market: MarketService
) -> None:
    """板のrollback snapshotは注文集合と次の注文IDを厳密に復元する。"""
    store = town._market_board_store
    snapshot = store.rollback_snapshot()
    _give(town, _LENA, _HERB, 1)
    added = market.place_sell_order(
        _LENA,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )

    store.restore_rollback_snapshot(snapshot)

    assert store.board().find(added.order_id) is None
    assert store.next_order_id() == added.order_id


class TestTheMerchantIsADoorOutOfTheWorld:
    """商人が受け取ったものは世界から消える。

    Phase 1 で商人の gold を無限と決めたのと同じ一本の理由から出ている。
    商人は世界の外との出入り口であって、世界の中に物を溜める主体ではない。

    在庫を持たせる案は却下した。商人が買った品をエージェントが買い戻せる形に
    なり、「商人を経由した転売」が最短の稼ぎ方になりかねない。値の形成を
    エージェント同士の板で見たいのに、商人が値の緩衝材になる。
    """

    def test_goods_sold_to_a_merchant_leave_the_world(
        self, town: Any, market: MarketService
    ) -> None:
        """商人の買い注文を受けると、渡した品はどこにも増えていない。"""
        market.place_merchant_buy_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=1,
        )
        _give(town, _LENA, _HERB, 1)
        before = _world_held(town, _HERB)
        order = market.board().orders[0]

        market.take_order(_LENA, order_id=order.order_id, quantity=1, current_tick=2)

        assert _world_held(town, _HERB) == before - 1

    def test_selling_to_a_merchant_still_pays_the_seller(
        self, town: Any, market: MarketService
    ) -> None:
        """商人へ売った側には、ちゃんと代金が入る (吸収されるのは品だけ)。"""
        market.place_merchant_buy_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=1,
        )
        _give(town, _LENA, _HERB, 1)
        before = _gold(town, _LENA)
        order = market.board().orders[0]

        market.take_order(_LENA, order_id=order.order_id, quantity=1, current_tick=2)

        assert _gold(town, _LENA) == before + 7

    def test_gold_paid_to_a_merchant_leaves_the_world(
        self, town: Any, market: MarketService
    ) -> None:
        """商人の売り注文を受けて払った gold は、どこにも増えていない。"""
        market.place_merchant_sell_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=1,
        )
        before = _world_gold(town)
        order = market.board().orders[0]

        market.take_order(_TOM, order_id=order.order_id, quantity=1, current_tick=2)

        assert _world_gold(town) == before - 7

    def test_buying_from_a_merchant_still_delivers_the_goods(
        self, town: Any, market: MarketService
    ) -> None:
        """商人から買った側には、ちゃんと品が届く。"""
        market.place_merchant_sell_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=1,
        )
        order = market.board().orders[0]

        market.take_order(_TOM, order_id=order.order_id, quantity=1, current_tick=2)

        assert _held(town, _TOM, _HERB) == 1

    def test_a_merchant_order_does_not_expire_into_someones_inventory(
        self, town: Any, market: MarketService
    ) -> None:
        """商人の注文が期限切れになっても、誰かの所持品には戻らない。

        戻す先の無い返却を書くと、商人 id をプレイヤー id として扱う経路が
        できてしまう。板から消えるだけで良い。
        """
        market.place_merchant_sell_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=1,
        )
        order = market.board().orders[0]
        before = _world_held(town, _HERB)

        market.expire_orders(current_tick=order.expires_at_tick + 1)

        assert market.board().orders == ()
        assert _world_held(town, _HERB) == before


class TestTheOwnerIsRecordedCorrectly:
    """注文の出し手が、エージェントか商人かで正しく分かれる。"""

    def test_a_player_order_is_owned_by_the_player(
        self, town: Any, market: MarketService
    ) -> None:
        """エージェントの出した注文は、そのエージェントのものになる。"""
        _give(town, _LENA, _HERB, 1)

        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        assert order.owner == MarketParticipant.player(_LENA)
        assert order.side is MarketOrderSide.SELL

    def test_a_merchant_order_is_owned_by_the_merchant(
        self, town: Any, market: MarketService
    ) -> None:
        """商人の出した注文は、その商人のものになる。"""
        order = market.place_merchant_buy_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=1,
        )

        assert order.owner == MarketParticipant.merchant(1)
        assert order.side is MarketOrderSide.BUY


class TestOnlyOneOrderPerItemAndSide:
    """同じ品目・同じ向きの自分の注文は、板に 1 件までしか置けない。

    これは**不変条件**であってツールの都合ではない。2 件あると
    `market_cancel` / `market_reprice` が「品目 + 向き」でどちらを指すのか
    決まらず、板の状態そのものが壊れている。番号で指す形は「表示に出ている
    名前をそのまま渡す」規約から外れるので採らない。

    値を変えたいときは reprice を使う、という形とも一貫する。「20G で 2 つ、
    18G で 3 つ」と刻んで出す市場作りの戦術は捨てるが、5 人 80 tick の世界で
    それは起きない。
    """

    def test_a_second_sell_order_for_the_same_item_is_refused(
        self, town: Any, market: MarketService
    ) -> None:
        """同じ品目の売り注文を 2 件目は出せない。"""
        _give(town, _LENA, _HERB, 2)
        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        with pytest.raises(MarketDuplicateOrderError):
            market.place_sell_order(
                _LENA, item_label=_HERB, quantity=1, unit_price=9, current_tick=2,
            )

    def test_the_opposite_side_is_still_allowed(
        self, town: Any, market: MarketService
    ) -> None:
        """向きが違えば出せる (正の対照)。

        同じ品を売りに出しながら、別の値で買い注文も出す形は禁じていない。
        指し先が「品目 + 向き」で一意に決まるため。
        """
        _give(town, _LENA, _HERB, 1)
        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.place_buy_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=5, current_tick=2,
        )

        assert len(market.board().orders) == 2

    def test_another_item_is_still_allowed(
        self, town: Any, market: MarketService
    ) -> None:
        """品目が違えば出せる (正の対照)。"""
        _give(town, _LENA, _HERB, 1)
        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.place_buy_order(
            _LENA, item_label=_BREAD, quantity=1, unit_price=5, current_tick=2,
        )

        assert len(market.board().orders) == 2

    def test_someone_elses_order_does_not_block_yours(
        self, town: Any, market: MarketService
    ) -> None:
        """他人が同じ品を出していても、自分は出せる (正の対照)。

        制限は「自分の注文が 2 件」を禁じるだけで、板の行数は制限しない。
        値の競争そのものが消えては意味が無い。
        """
        _give(town, _LENA, _HERB, 1)
        _give(town, _TOM, _HERB, 1)
        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )

        market.place_sell_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=9, current_tick=2,
        )

        assert len(market.board().orders) == 2

    def test_an_order_awaiting_collection_blocks_a_new_one(
        self, town: Any, market: MarketService
    ) -> None:
        """引き取り待ちの注文も 1 件に数える。

        数えないと、引き取り待ちの薬草の売り注文が残ったまま新しい薬草の売り
        注文を出せてしまい、取り下げがどちらを指すか決まらない。断り文は
        「先に預けたままのものを引き取ってください」で、次の一手が違うので
        重複とは別のエラーにする。
        """
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        _fill_inventory(town, _LENA, _HERB)
        market.expire_orders(current_tick=order.expires_at_tick + 1)

        with pytest.raises(MarketOrderAwaitingCollectionError):
            market.place_sell_order(
                _LENA, item_label=_HERB, quantity=1, unit_price=9, current_tick=99,
            )

    def test_a_refused_second_order_costs_nothing(
        self, town: Any, market: MarketService
    ) -> None:
        """2 件目が断られたとき、品も gold も動かない (正の対照)。"""
        _give(town, _LENA, _HERB, 2)
        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        held = _held(town, _LENA, _HERB)

        with pytest.raises(MarketDuplicateOrderError):
            market.place_sell_order(
                _LENA, item_label=_HERB, quantity=1, unit_price=9, current_tick=2,
            )

        assert _held(town, _LENA, _HERB) == held
        assert len(market.board().orders) == 1

    def test_a_cancelled_order_frees_the_slot(
        self, town: Any, market: MarketService
    ) -> None:
        """取り下げれば、同じ品目でまた出せる。

        制限が「永久に 1 回だけ」にならないことを見る。
        """
        _give(town, _LENA, _HERB, 1)
        order = market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        market.cancel_order(_LENA, order_id=order.order_id)

        market.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=9, current_tick=2,
        )

        assert len(market.board().orders) == 1
