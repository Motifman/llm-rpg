"""板の値動きが、trace から時系列として引ける (経済統合 Phase 3)。

ユーザーが見たいのは「価格が動的に変わるところ」なので、**run が終わったあとに
品目ごとの値の推移を引けること**が最優先の観測要件になる。

「イベントが出ている」ではなく「**時系列が引ける**」まで見る。個々のイベントが
出ていても、単価が載っていない・約定がまとめられている・値付けと約定が別形式、
のどれかがあると時系列にならない。

2 種類の推移を両方引けるようにする。**値付けの推移** (出品と値の付け直し) と、
**約定の時系列** (実際にいくらで売れたか)。run 後にどちらを見たいかは、run を
見てから決められる方がよい。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_MINA = PlayerId(3)
_BREAD = "焼きたてのパン"
_HERB = "薬草"


class _CapturingTraceRecorder:
    """記録された trace をそのまま覚えておくだけの recorder。"""

    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, Any]]] = []

    def record(self, kind, **payload) -> None:
        self.records.append((str(getattr(kind, "value", kind)), payload))


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    for pid, name in (("tom", "トム"), ("mina", "ミナ")):
        raw["players"].append({
            "id": pid, "name": name, "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 500,
            "persona_prompt": f"あなたは{name}。",
        })
    raw["market"] = {"board_spot": "market_square"}
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    runtime = create_world_runtime(str(path))
    runtime.set_trace_recorder(_CapturingTraceRecorder())
    return runtime


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    grant_item_specs_to_inventory(
        player_id,
        tuple(ItemSpecId.create(_spec_id(runtime, label)) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _list_bread(runtime: Any, seller: PlayerId, *, quantity: int, price: int) -> Any:
    _give(runtime, seller, _BREAD, quantity)
    return runtime._market_service.place_sell_order(
        seller, item_label=_BREAD, quantity=quantity, unit_price=price,
        current_tick=runtime.current_tick(),
    )


def _market_events(runtime: Any) -> List[Dict[str, Any]]:
    return [
        payload
        for kind, payload in runtime._trace_recorder.records
        if kind == "market_activity"
    ]


def _price_series(runtime: Any, item_name: str, kinds: Tuple[str, ...]) -> List[Tuple[int, int]]:
    """trace から、その品目の (手番, 単価) の並びを組み立てる。

    **これができることが要件**。run 後の分析はこの形で値動きを読む。
    """
    return [
        (event["tick"], event["unit_price"])
        for event in _market_events(runtime)
        if event["item_name"] == item_name and event["market_event"] in kinds
    ]


class TestEveryMoveOnTheBoardLeavesALine:
    """板の上の 5 種の動きが、すべて trace に残る。"""

    def test_a_listing_is_recorded_with_its_price(self, town: Any) -> None:
        """出品が、品目・個数・単価・出し手つきで残る。"""
        _list_bread(town, _LENA, quantity=2, price=20)

        (event,) = _market_events(town)
        assert event["market_event"] == "listed"
        assert event["item_name"] == _BREAD
        assert event["quantity"] == 2
        assert event["unit_price"] == 20
        assert event["actor_name"] == "レナ"

    def test_a_reprice_records_both_prices(self, town: Any) -> None:
        """値の付け直しが、旧値と新値の両方つきで残る。

        旧値が無いと、値が動いたのか最初からその値だったのかを後から
        区別できない。
        """
        _list_bread(town, _LENA, quantity=2, price=20)
        town._market_service.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        event = _market_events(town)[-1]
        assert event["market_event"] == "repriced"
        assert event["old_unit_price"] == 20
        assert event["unit_price"] == 18

    def test_a_settlement_records_both_sides_and_the_taker(self, town: Any) -> None:
        """約定が、売り手・買い手・受けた側つきで残る。

        `taker_side` は**値を決めたのがどちらか**を読むために要る。売り注文が
        受けられたなら値は売り手が付けた値。これが無いと時系列は引けても
        「誰が値を動かしたか」が読めない。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        event = _market_events(town)[-1]
        assert event["market_event"] == "settled"
        assert event["seller_name"] == "レナ"
        assert event["buyer_name"] == "トム"
        assert event["taker_side"] == "buy"
        assert event["unit_price"] == 18
        assert event["total_gold"] == 18

    def test_a_cancellation_is_recorded(self, town: Any) -> None:
        """取り下げが残る。"""
        _list_bread(town, _LENA, quantity=1, price=20)
        town._market_service.cancel_by(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL,
        )

        assert _market_events(town)[-1]["market_event"] == "cancelled"

    def test_an_expiry_is_recorded(self, town: Any) -> None:
        """期限切れが残る。

        **ツールの呼び出しが無い唯一の動き**なので、行動記録からは辿れない。
        板が痩せていく理由を後から読むにはこれが要る。
        """
        order = _list_bread(town, _LENA, quantity=1, price=20)
        town._market_service.expire_orders(current_tick=order.expires_at_tick + 1)

        assert _market_events(town)[-1]["market_event"] == "expired"


class TestASweepLeavesOneLinePerFill:
    """またいで買うと、約定は 1 件ずつ残る。"""

    def test_two_listings_leave_two_lines(self, town: Any) -> None:
        """18G と 20G の出品にまたがって買うと、trace は 2 件になる。

        単価が違うものを 1 件にまとめると、まさに見たい価格の時系列が壊れる。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _list_bread(town, _MINA, quantity=2, price=20)

        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=3, current_tick=town.current_tick(),
        )

        settled = [e for e in _market_events(town) if e["market_event"] == "settled"]
        assert [e["unit_price"] for e in settled] == [18, 20]
        assert [e["quantity"] for e in settled] == [1, 2]


class TestThePriceSeriesCanBeRebuilt:
    """run が終わったあと、品目ごとの値の推移を組み立てられる。"""

    def test_the_listed_price_series_is_recoverable(self, town: Any) -> None:
        """値付けの推移 (出品と値の付け直し) が時系列になる。"""
        _list_bread(town, _LENA, quantity=3, price=25)
        town._market_service.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=22,
        )
        town._market_service.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=19,
        )

        series = _price_series(town, _BREAD, ("listed", "repriced"))

        assert [price for _tick, price in series] == [25, 22, 19]

    def test_the_settled_price_series_is_recoverable(self, town: Any) -> None:
        """約定の時系列 (実際にいくらで売れたか) が引ける。"""
        _list_bread(town, _LENA, quantity=1, price=25)
        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )
        _list_bread(town, _MINA, quantity=1, price=19)
        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        series = _price_series(town, _BREAD, ("settled",))

        assert [price for _tick, price in series] == [25, 19]

    def test_the_two_series_do_not_mix(self, town: Any) -> None:
        """値付けと約定は別々に引ける (正の対照)。

        同じ形式で混ざっていると、「出した値」と「売れた値」の区別が
        できない。売れ残りの値下げを約定と数えると、相場が実際より安く見える。
        """
        _list_bread(town, _LENA, quantity=1, price=25)
        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        assert len(_price_series(town, _BREAD, ("listed", "repriced"))) == 1
        assert len(_price_series(town, _BREAD, ("settled",))) == 1

    def test_each_item_has_its_own_series(self, town: Any) -> None:
        """品目ごとに分かれる。"""
        _list_bread(town, _LENA, quantity=1, price=25)
        _give(town, _MINA, _HERB, 1)
        town._market_service.place_sell_order(
            _MINA, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )

        assert [p for _t, p in _price_series(town, _BREAD, ("listed",))] == [25]
        assert [p for _t, p in _price_series(town, _HERB, ("listed",))] == [8]

    def test_the_series_carries_the_tick(self, town: Any) -> None:
        """各点に手番が入っている (時系列として並べられる)。"""
        _list_bread(town, _LENA, quantity=1, price=25)

        ((tick, _price),) = _price_series(town, _BREAD, ("listed",))
        assert tick == town.current_tick()
