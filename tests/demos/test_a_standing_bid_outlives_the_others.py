"""板に居座り続ける買い注文を、シナリオが宣言できる (経済統合 Phase 3)。

交差 (売り注文と買い注文が同じ品に並ぶ) は 5 run 続けて 0 だった。**測った
ところ、理由は滞留ではなく「すれ違い」だった。**

| run | 商人の買い注文 | 人が出した品 |
|---|---|---|
| v3.4 | 薬草 (t0〜t25) | パン t27 以降 / **薬草 t31** / 麦束 t41 以降 |
| v3.5 | 薬草 (t0〜t25) | パン t16 以降 / 麦束 t35 以降 (薬草は 1 度も出ず) |

v3.4 の薬草は t31 に出ていて、買い注文は t25 に流れたあとだった。**6 tick 差**
で交差を逃している。「機会が構造的に無い」ではなく、すれ違っただけだった。

そこで**注文ごとに寿命を宣言できる**ようにする。人が実際に作る品へ、取引の
範囲の中の値で、run を通して居座る買い注文を 1 件置く。**気づく対象が実在
しないと、気づくかどうかは測れない。**

**「期限なし」ではなく長い期限にした。** 期限の無い注文を作ると
``expires_at_tick`` が Optional になり、codec・復元・期限切れ stage の全部に
「無い」の分岐が増える。80 tick の run に 999 を書けば同じことが起きるので、
**世界の状態を増やさない方を採った**。ただし同じものではない — 十分に長い run
では流れる。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

_TOWN = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
)
_BREAD_SPEC = "bread"


def _town(tmp_path: pathlib.Path, initial_orders: list, **market: Any) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["market"] = {
        "board_spot": "market_square",
        "order_expires_in_ticks": 24,
        "initial_orders": initial_orders,
        **market,
    }
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _bid(**overrides: Any) -> Dict[str, Any]:
    order = {
        "merchant": "gustav", "side": "buy", "item_spec": _BREAD_SPEC,
        "quantity": 5, "unit_price": 12,
    }
    order.update(overrides)
    return order


def _only_order(runtime: Any) -> Any:
    (order,) = runtime._market_service.board().orders
    return order


class TestAnOrderCanDeclareItsOwnLifetime:
    """初期注文は、板ぜんたいの既定と別の寿命を持てる。"""

    def test_without_a_declaration_it_uses_the_board_default(
        self, tmp_path: pathlib.Path
    ) -> None:
        """寿命を書かない注文は、板の既定 (24 手番) で流れる。

        既定を変えると、v3.5 と比べられなくなる。**既存の宣言の意味は
        動かさない。**
        """
        runtime = _town(tmp_path, [_bid()])

        assert _only_order(runtime).expires_at_tick == 24

    def test_a_declared_lifetime_wins(self, tmp_path: pathlib.Path) -> None:
        """寿命を書いた注文は、その手番数だけ板に居る。"""
        runtime = _town(tmp_path, [_bid(expires_in_ticks=999)])

        assert _only_order(runtime).expires_at_tick == 999

    def test_it_is_still_there_after_the_board_default_has_passed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """板の既定を過ぎても、宣言した注文は流れない。

        **これが目的そのもの。** 買い注文が run の途中で消えると、そのあとに
        出た売り注文とはすれ違う。
        """
        runtime = _town(tmp_path, [_bid(expires_in_ticks=999)])

        runtime._market_service.expire_orders(current_tick=40)

        assert len(runtime._market_service.board().orders) == 1

    def test_the_others_still_expire_around_it(self, tmp_path: pathlib.Path) -> None:
        """居座る注文の隣で、既定の注文はこれまでどおり流れる (**正の対照**)。

        全部が居座るようになっていたら、この宣言は何も足していない。
        """
        runtime = _town(tmp_path, [
            _bid(expires_in_ticks=999),
            _bid(side="sell", unit_price=24, quantity=1),
        ])

        runtime._market_service.expire_orders(current_tick=40)

        (left,) = runtime._market_service.board().orders
        assert left.side.value == "buy"

    def test_a_lifetime_the_world_cannot_have_is_refused_at_startup(
        self, tmp_path: pathlib.Path
    ) -> None:
        """0 以下の寿命を書くと、起動時に落ちる。

        黙って既定へ倒すと、作者は「すぐ流れる注文」を宣言したつもりで
        24 手番居座る注文を作る。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _town(tmp_path, [_bid(expires_in_ticks=0)])

        assert "expires_in_ticks" in str(caught.value)


class TestTheStandingBidMakesACrossingPossible:
    """居座る買い注文があると、あとから出た売り注文と同じ品に並ぶ。"""

    def test_a_later_listing_meets_the_bid_that_is_still_there(
        self, tmp_path: pathlib.Path
    ) -> None:
        """買い注文が流れたあとに出る売り注文でも、同じ品に並ぶ。

        v3.4 で実際に起きたすれ違い (買い t25 に流れる / 売り t31 に出る) が、
        この宣言で起きなくなることを見る。
        """
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        runtime = _town(tmp_path, [_bid(expires_in_ticks=999, unit_price=12)])
        lena = PlayerId(1)
        spec_id = runtime._item_spec_repo.find_by_name("焼きたてのパン").item_spec_id.value
        grant_item_specs_to_inventory(
            lena, (ItemSpecId.create(spec_id),), runtime._item_repo,
            runtime._item_spec_repo, runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )
        runtime._market_service.expire_orders(current_tick=31)

        runtime._market_service.place_sell_order(
            lena, item_label="焼きたてのパン", quantity=1, unit_price=8,
            current_tick=31,
        )

        board = runtime._market_service.board()
        sides = {o.side.value for o in board.orders if o.item_spec_id == spec_id}
        assert sides == {"buy", "sell"}
