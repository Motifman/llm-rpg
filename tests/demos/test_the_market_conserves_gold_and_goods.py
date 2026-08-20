"""市場を一巡しても、gold と品の総量が変わらない (経済統合 Phase 3)。

預け先が 4 つに増えた — 所持品 / 板の品 (売り注文) / 板の gold (買い注文) /
地面。**どこかで 1 つ増えて 1 つ減る取り違えは、個別のテストだと両方が
「期待どおり」に見えて通ります。** 合計で見ると落ちます。

**商人の絡む取引は除外します。** 商人は世界の外との出入り口で、gold は湧き、
品は消えるのが正しい (design_decisions #112)。除外を暗黙にすると、後から読む人に
「測れなかった」と区別がつかないので、**商人を絡めると総量が変わることも
1 件見ておきます**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from tests.support.overflow_sinks import IGNORE_OVERFLOW

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_PLAYERS = (PlayerId(1), PlayerId(2), PlayerId(3))
_LENA, _TOM, _MINA = _PLAYERS
_HERB = "薬草"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"][0]["initial_gold"] = 300
    spawn = raw["players"][0]["spawn_spot"]
    for pid, name in (("tom", "トム"), ("mina", "ミナ")):
        raw["players"].append({
            "id": pid, "name": name, "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 300,
            "persona_prompt": f"あなたは{name}。",
        })
    raw["market"] = {"board_spot": "market_square"}
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


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


def _totals(runtime: Any, label: str) -> Tuple[int, int]:
    """世界にある gold と品の総量を数える。

    **預け先を全部足す。** どれか 1 つを数え忘れると、移動を消失と読み違える。
    """
    spec_id = _spec_id(runtime, label)

    gold = sum(
        runtime._player_status_repo.find_by_id(pid).gold.value for pid in _PLAYERS
    )
    goods = 0
    for pid in _PLAYERS:
        inventory = runtime._player_inventory_repo.find_by_id(pid)
        counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
        goods += sum(c for s, c in counts.items() if s.value == spec_id)

    for order in runtime._market_service.board().orders:
        if order.side is MarketOrderSide.BUY:
            # 買い注文は gold を預かっている。
            gold += order.total_gold
        elif order.item_spec_id == spec_id:
            # 売り注文は品を預かっている。
            goods += order.quantity

    for spot_id in _all_spot_ids(runtime):
        interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
        if interior is None:
            continue
        goods += sum(
            1 for item in interior.ground_items if item.item_spec_id.value == spec_id
        )
    return gold, goods


def _all_spot_ids(runtime: Any):
    """世界の全 spot。地面を数え漏らすと、移動を消失と読み違える。"""
    graph = runtime._spot_graph_repo.find_graph()
    return list(graph._spots.keys())


class TestNothingIsCreatedOrDestroyedBetweenAgents:
    """エージェント同士の取引では、gold も品も増えも減りもしない。"""

    def test_a_sell_order_taken_conserves_everything(self, town: Any) -> None:
        """出品 → 買われる、で総量が変わらない。"""
        _give(town, _LENA, _HERB, 2)
        before = _totals(town, _HERB)
        town._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=2, unit_price=8,
            current_tick=town.current_tick(),
        )
        town._market_service.buy_best(
            _TOM, item_label=_HERB, quantity=2, current_tick=town.current_tick(),
        )

        assert _totals(town, _HERB) == before

    def test_a_bid_taken_conserves_everything(self, town: Any) -> None:
        """買い注文 → 売られる、で総量が変わらない。"""
        _give(town, _LENA, _HERB, 2)
        before = _totals(town, _HERB)
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=2, unit_price=8,
            current_tick=town.current_tick(),
        )
        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=2, current_tick=town.current_tick(),
        )

        assert _totals(town, _HERB) == before

    def test_goods_left_at_the_board_are_still_counted(self, town: Any) -> None:
        """買い手が受け取れず板の足元に置かれても、総量は変わらない。

        **地面を数え忘れると、ここで「消えた」ように見えます。**
        """
        _give(town, _LENA, _HERB, 1)
        while not town._player_inventory_repo.find_by_id(_TOM).is_inventory_full():
            _give(town, _TOM, _HERB, 1)
        before = _totals(town, _HERB)
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert _totals(town, _HERB) == before

    def test_cancelling_conserves_everything(self, town: Any) -> None:
        """出品 → 取り下げ、買い注文 → 取り下げ、どちらも総量が戻る。"""
        _give(town, _LENA, _HERB, 2)
        before = _totals(town, _HERB)
        town._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=2, unit_price=8,
            current_tick=town.current_tick(),
        )
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=5,
            current_tick=town.current_tick(),
        )
        town._market_service.cancel_by(
            _LENA, item_label=_HERB, side=MarketOrderSide.SELL,
        )
        town._market_service.cancel_by(
            _TOM, item_label=_HERB, side=MarketOrderSide.BUY,
        )

        assert _totals(town, _HERB) == before

    def test_repricing_a_bid_conserves_gold(self, town: Any) -> None:
        """買い注文の値を上げ下げしても、gold の総量は変わらない。

        差額の預け入れ・払い戻しで**片方だけ動かす**と、ここで落ちます。
        """
        before = _totals(town, _HERB)
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=2, unit_price=8,
            current_tick=town.current_tick(),
        )
        town._market_service.reprice_order(
            _TOM, item_label=_HERB, side=MarketOrderSide.BUY, new_unit_price=12,
        )
        town._market_service.reprice_order(
            _TOM, item_label=_HERB, side=MarketOrderSide.BUY, new_unit_price=6,
        )

        assert _totals(town, _HERB) == before

    def test_a_full_round_trip_conserves_everything(self, town: Any) -> None:
        """買い注文 → 売られる → 受け取れず板へ → 拾う、まで通しても変わらない。"""
        _give(town, _LENA, _HERB, 1)
        while not town._player_inventory_repo.find_by_id(_TOM).is_inventory_full():
            _give(town, _TOM, _HERB, 1)
        before = _totals(town, _HERB)
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )
        town._item_transfer_service.pickup_item(
            _MINA, _first_ground_item(town, _HERB),
        )

        assert _totals(town, _HERB) == before


class TestTheMerchantIsAllowedToBreakConservation:
    """商人が絡むと総量は変わる。**それが設計**で、測れないからではない。"""

    def test_selling_to_a_merchant_removes_goods_from_the_world(self, town: Any) -> None:
        """商人の買い注文へ売ると、品が世界から減る。

        商人は世界の外との出入り口 (#112)。上の保存テストが商人を除外して
        いるのは、数えにくいからではなく**そういう設計だから**である、と
        いうことをここで固定しておく。
        """
        town._market_service.place_merchant_buy_order(
            merchant_id=1, item_spec_id=_spec_id(town, _HERB),
            quantity=1, unit_price=7, current_tick=town.current_tick(),
        )
        _give(town, _LENA, _HERB, 1)
        _gold_before, goods_before = _totals(town, _HERB)

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        _gold_after, goods_after = _totals(town, _HERB)
        assert goods_after == goods_before - 1


def _first_ground_item(runtime: Any, label: str):
    spec_id = _spec_id(runtime, label)
    for spot_id in _all_spot_ids(runtime):
        interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
        if interior is None:
            continue
        for item in interior.ground_items:
            if item.item_spec_id.value == spec_id:
                return item.item_instance_id
    raise AssertionError("地面に品がありません")
