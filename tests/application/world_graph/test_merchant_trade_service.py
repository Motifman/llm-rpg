"""NPC 商人との売買で gold と所持品が動く挙動 (経済統合 Phase 1)。

買いと売りは**全量成功か 0 か**で、部分成功を作らない。金銭が動く操作で
「3 個買おうとして 2 個買えた」を許すと、run 全体の gold 流量を trace から
追うときに会計が合わなくなる。

失敗は原因ごとに分ける。「買えなかった」だけでは、金が足りないのか品を
扱っていないのか商人が居ないのかが分からず、次の一手が決まらない。
"""

from __future__ import annotations

import json
import pathlib
import tempfile
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_graph.spot_graph_merchant_trade_service import (
    MerchantDoesNotBuyError,
    MerchantDoesNotSellError,
    MerchantNotAtSpotError,
    NotEnoughGoldError,
    NotEnoughItemsToSellError,
    PurchaseInventoryFullError,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    pathlib.Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)
_BUYER = PlayerId(1)


def _world(
    *,
    initial_gold: int = 100,
    sells_price: int = 10,
    buys_price: int = 6,
    second_merchant: bool = False,
) -> Any:
    """商人 1 人 (必要なら 2 人) と所持金を宣言した world runtime を組む。"""
    raw: Dict[str, Any] = json.loads(_DRILL.read_text(encoding="utf-8"))
    spawn_spot = raw["players"][0]["spawn_spot"]
    traded = raw["item_specs"][0]["id"]
    raw["merchants"] = [
        {
            "id": "gustav",
            "name": "商人グスタフ",
            "spot": spawn_spot,
            "sells": [{"item_spec": traded, "price": sells_price}],
            "buys": [{"item_spec": traded, "price": buys_price}],
        }
    ]
    if second_merchant:
        raw["merchants"].append(
            {
                "id": "martha",
                "name": "商人マーサ",
                "spot": spawn_spot,
                "sells": [{"item_spec": traded, "price": sells_price - 2}],
            }
        )
    raw["players"][0]["initial_gold"] = initial_gold
    path = pathlib.Path(tempfile.mkdtemp()) / "econ.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    runtime = create_world_runtime(path)
    return runtime


def _traded_spec_id(runtime: Any) -> int:
    return runtime.scenario.merchants[0].sells[0].item_spec_id


def _merchant_id(runtime: Any, index: int = 0) -> int:
    return runtime.scenario.merchants[index].merchant_id


def _gold_of(runtime: Any, player_id: PlayerId = _BUYER) -> int:
    return runtime._player_status_repo.find_by_id(player_id).gold.value


def _owned_count(runtime: Any, spec_id: int, player_id: PlayerId = _BUYER) -> int:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        count_owned_item_instances_by_spec,
    )
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return counts.get(ItemSpecId.create(spec_id), 0)


def _move_away(runtime: Any, player_id: PlayerId) -> None:
    """商人と同席していない場所へプレイヤーを移す。"""
    graph = runtime._spot_graph_repo.find_graph()
    merchant_spot = runtime.scenario.merchants[0].spot_id
    other = next(
        node.spot_id
        for node in graph.iter_spot_nodes()
        if node.spot_id != merchant_spot
    )
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(EntityId.create(int(player_id)), SpotId.create(other.value))
    runtime._spot_graph_repo.save(graph)


class TestBuyingFromAMerchant:
    """買いが gold を減らし、所持品を増やす挙動を保証する。"""

    def test_buying_one_item_moves_gold_and_inventory(self) -> None:
        """1 つ買うと、所持金が価格ぶん減り、その品が 1 つ増える。"""
        runtime = _world(initial_gold=100, sells_price=10)
        spec_id = _traded_spec_id(runtime)
        before = _owned_count(runtime, spec_id)

        runtime._merchant_trade_service.buy(
            _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=1,
        )

        assert _gold_of(runtime) == 90
        assert _owned_count(runtime, spec_id) == before + 1

    def test_buying_several_items_charges_the_total(self) -> None:
        """数量 2 で買うと合計額が引かれ、その品が 2 つ増える。"""
        runtime = _world(initial_gold=100, sells_price=10)
        spec_id = _traded_spec_id(runtime)
        before = _owned_count(runtime, spec_id)

        result = runtime._merchant_trade_service.buy(
            _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=2,
        )

        assert _gold_of(runtime) == 80
        assert _owned_count(runtime, spec_id) == before + 2
        assert result.gold_delta == -20
        assert result.quantity == 2

    def test_not_enough_gold_leaves_everything_untouched(self) -> None:
        """所持金が足りないとき、金も所持品も動かさずに失敗する (部分的に買わない)。"""
        runtime = _world(initial_gold=25, sells_price=10)
        spec_id = _traded_spec_id(runtime)
        before = _owned_count(runtime, spec_id)

        with pytest.raises(NotEnoughGoldError) as excinfo:
            runtime._merchant_trade_service.buy(
                _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=3,
            )

        assert _gold_of(runtime) == 25
        assert _owned_count(runtime, spec_id) == before
        # 不足額を文面に出す。「足りない」だけでは、あと何を売れば届くか決められない。
        assert "5" in str(excinfo.value)

    def test_buying_an_item_the_merchant_does_not_sell_is_rejected(self) -> None:
        """その商人が売っていない品を買おうとすると、扱う品を添えて失敗する。"""
        runtime = _world()
        traded = _traded_spec_id(runtime)
        other_spec = next(
            definition.spec_id.value
            for definition in runtime.scenario.item_spec_definitions
            if definition.spec_id.value != traded
        )

        with pytest.raises(MerchantDoesNotSellError):
            runtime._merchant_trade_service.buy(
                _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=other_spec, quantity=1,
            )

        assert _gold_of(runtime) == 100

    def test_buying_without_the_merchant_present_is_rejected(self) -> None:
        """商人と同席していない場所では買えない (店の位置が意味を持つ)。"""
        runtime = _world()
        spec_id = _traded_spec_id(runtime)
        _move_away(runtime, _BUYER)

        with pytest.raises(MerchantNotAtSpotError):
            runtime._merchant_trade_service.buy(
                _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=1,
            )

        assert _gold_of(runtime) == 100

    def test_a_full_inventory_blocks_the_purchase_before_paying(self) -> None:
        """インベントリに空きが足りないとき、金を払う前に失敗する。"""
        runtime = _world(initial_gold=1000, sells_price=1)
        spec_id = _traded_spec_id(runtime)
        inventory = runtime._player_inventory_repo.find_by_id(_BUYER)
        free_slots = sum(
            1 for _slot, instance in inventory.iter_slots() if instance is None
        )

        with pytest.raises(PurchaseInventoryFullError):
            runtime._merchant_trade_service.buy(
                _BUYER,
                merchant_id=_merchant_id(runtime),
                item_spec_id=spec_id,
                quantity=free_slots + 1,
            )

        assert _gold_of(runtime) == 1000


class TestSellingToAMerchant:
    """売りが gold を増やし、所持品を減らす挙動を保証する。"""

    def test_selling_one_item_moves_gold_and_inventory(self) -> None:
        """1 つ売ると、所持金が買値ぶん増え、その品が 1 つ減る。"""
        runtime = _world(initial_gold=0, buys_price=6)
        spec_id = _traded_spec_id(runtime)
        # 売る品を用意する (買ってから売ると、買値と売値の差が結果に混ざる)。
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

        grant_item_specs_to_inventory(
            _BUYER,
            (ItemSpecId.create(spec_id),),
            runtime._item_repo,
            runtime._item_spec_repo,
            runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )
        before = _owned_count(runtime, spec_id)

        result = runtime._merchant_trade_service.sell(
            _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=1,
        )

        assert _gold_of(runtime) == 6
        assert _owned_count(runtime, spec_id) == before - 1
        assert result.gold_delta == 6

    def test_selling_more_than_owned_leaves_everything_untouched(self) -> None:
        """所持数より多く売ろうとすると、所持数を添えて失敗し、金も品も動かない。"""
        runtime = _world(initial_gold=0)
        spec_id = _traded_spec_id(runtime)

        with pytest.raises(NotEnoughItemsToSellError):
            runtime._merchant_trade_service.sell(
                _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=1,
            )

        assert _gold_of(runtime) == 0

    def test_selling_an_item_the_merchant_does_not_buy_is_rejected(self) -> None:
        """その商人が買い取らない品を売ろうとすると、買い取る品を添えて失敗する。"""
        runtime = _world(initial_gold=0, second_merchant=True)
        spec_id = _traded_spec_id(runtime)

        with pytest.raises(MerchantDoesNotBuyError):
            # マーサは売るだけで買い取らない。
            runtime._merchant_trade_service.sell(
                _BUYER, merchant_id=_merchant_id(runtime, 1), item_spec_id=spec_id, quantity=1,
            )

        assert _gold_of(runtime) == 0

    def test_selling_without_the_merchant_present_is_rejected(self) -> None:
        """商人と同席していない場所では売れない。"""
        runtime = _world(initial_gold=0)
        spec_id = _traded_spec_id(runtime)
        _move_away(runtime, _BUYER)

        with pytest.raises(MerchantNotAtSpotError):
            runtime._merchant_trade_service.sell(
                _BUYER, merchant_id=_merchant_id(runtime), item_spec_id=spec_id, quantity=1,
            )
