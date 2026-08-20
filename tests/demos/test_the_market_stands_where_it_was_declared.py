"""宣言した市場が、実際に世界の中に立っている (経済統合 Phase 3)。

シナリオに書いたのに効いていない、が**この repo でいちばん多い静かな失敗**
(#830 / #840)。読み取りのテストと配線のテストは別物なので、両方を書く。

板がまだツールから触れない段 (この PR) でも、世界を作った時点で板が立って
いること・初期注文が並んでいることは確かめられる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"


def _build(tmp_path: Path, market: Dict[str, Any] | None) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    if market is not None:
        raw["market"] = market
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


class TestTheBoardStandsInTheDeclaredPlace:
    """板は、宣言した場所に立つ。"""

    def test_the_board_has_a_place_in_a_world_that_declares_one(
        self, tmp_path: Path
    ) -> None:
        """市場を宣言した世界では、板の置き場所が決まっている。"""
        runtime = _build(tmp_path, {"board_spot": "market_square"})

        assert runtime._market_board_store.board_spot_id is not None

    def test_a_world_without_a_market_has_no_board(self, tmp_path: Path) -> None:
        """市場を宣言していない世界には板が無い (正の対照)。

        既存シナリオを 1 つも書き換えずに、過去 run との比較可能性を保つ。
        """
        runtime = _build(tmp_path, None)

        assert runtime._market_board_store.board_spot_id is None
        assert runtime._market_service.board().orders == ()

    def test_the_declared_expiry_reaches_the_orders(self, tmp_path: Path) -> None:
        """宣言した期限が、実際に作られる注文の期限まで届いている。

        読めているのに配線されていないと、シナリオに書いたのに効かない静かな
        失敗になる。
        """
        runtime = _build(tmp_path, {
            "board_spot": "market_square",
            "order_expires_in_ticks": 33,
            "initial_orders": [
                {"merchant": "gustav", "side": "sell", "item_spec": "herb",
                 "quantity": 1, "unit_price": 9},
            ],
        })

        (order,) = runtime._market_service.board().orders
        assert order.expires_at_tick == order.listed_at_tick + 33

    def test_the_engine_default_applies_without_a_declaration(
        self, tmp_path: Path
    ) -> None:
        """期限を書かなければ engine の既定 (40 手番) のままになる。

        正の対照。宣言を読む経路を壊したときに、上のテストだけだと「既定へ
        倒れた」ことに気付けない。
        """
        runtime = _build(tmp_path, {
            "board_spot": "market_square",
            "initial_orders": [
                {"merchant": "gustav", "side": "sell", "item_spec": "herb",
                 "quantity": 1, "unit_price": 9},
            ],
        })

        (order,) = runtime._market_service.board().orders
        assert order.expires_at_tick == order.listed_at_tick + 40


class TestTheDeclaredOrdersAreOnTheBoardFromTheStart:
    """初期注文は、世界が始まった時点で板に並んでいる。"""

    def test_a_declared_sell_order_is_standing(self, tmp_path: Path) -> None:
        """宣言した売り注文が、商人名義で板に並んでいる。"""
        runtime = _build(tmp_path, {
            "board_spot": "market_square",
            "initial_orders": [
                {"merchant": "gustav", "side": "sell", "item_spec": "herb",
                 "quantity": 2, "unit_price": 9},
            ],
        })

        (order,) = runtime._market_service.board().orders
        assert order.side is MarketOrderSide.SELL
        assert order.quantity == 2
        assert order.unit_price_gold == 9
        assert order.owner.is_merchant is True

    def test_a_declared_buy_order_is_standing(self, tmp_path: Path) -> None:
        """宣言した買い注文も、同じように板に並んでいる。"""
        runtime = _build(tmp_path, {
            "board_spot": "market_square",
            "initial_orders": [
                {"merchant": "gustav", "side": "buy", "item_spec": "herb",
                 "quantity": 3, "unit_price": 7},
            ],
        })

        (order,) = runtime._market_service.board().orders
        assert order.side is MarketOrderSide.BUY
        assert order.owner == MarketParticipant.merchant(order.owner.entity_id)

    def test_several_orders_keep_their_own_prices(self, tmp_path: Path) -> None:
        """同じ品目の初期注文を複数置くと、それぞれの値で並ぶ。

        「昨日の売れ残り」を別々の値で置けることが、最初の手番から**値の比較**が
        起きる条件になる。1 件しか置けないと、比べる相手が居ない。
        """
        runtime = _build(tmp_path, {
            "board_spot": "market_square",
            "initial_orders": [
                {"merchant": "gustav", "side": "sell", "item_spec": "herb",
                 "quantity": 1, "unit_price": 9},
                {"merchant": "gustav", "side": "sell", "item_spec": "herb",
                 "quantity": 1, "unit_price": 11},
            ],
        })

        prices = sorted(o.unit_price_gold for o in runtime._market_service.board().orders)
        assert prices == [9, 11]

    def test_an_empty_declaration_leaves_the_board_empty(self, tmp_path: Path) -> None:
        """初期注文を書かなければ、板は空で始まる (正の対照)。"""
        runtime = _build(tmp_path, {"board_spot": "market_square"})

        assert runtime._market_service.board().orders == ()
