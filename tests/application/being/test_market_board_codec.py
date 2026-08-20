"""板は中断・再開をまたいで残る (経済統合 Phase 3)。

**store を足す PR で同時に入れる。** 「あとで足す」と長走実験の終了 → 再開で
連続性が静かに壊れる。しかも板の場合は、板が消えると**預けた品と gold が
まるごと消滅する** — 出品者の所持品からは既に引かれているので、戻す先を失う。
Phase 2 の「提案だけ消えて凍結が残る」と同じ型の事故で、症状が出るのは再開して
しばらく経ってからになる。

形だけ戻って参照が切れていないかまで見る。「復元後の板から実際に買える」を
確かめないと、`orders` の中身は一致しているのに約定できない状態を見逃す。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.being.world_subsystems.market_board_codec import (
    MarketBoardSubsystemCodec,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOWN = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


def _build(tmp_path: Path) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"].append({
        "id": "tom", "name": "トム",
        "spawn_spot": raw["players"][0]["spawn_spot"],
        "initial_items": [], "initial_gold": 100,
        "persona_prompt": "あなたはトム。",
    })
    raw["market"] = {"board_spot": "market_square", "order_expires_in_ticks": 40}
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

    spec_id = runtime._item_spec_repo.find_by_name(label).item_spec_id.value
    grant_item_specs_to_inventory(
        player_id,
        tuple(ItemSpecId.create(spec_id) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _gold(runtime: Any, player_id: PlayerId) -> int:
    return runtime._player_status_repo.find_by_id(player_id).gold.value


@pytest.fixture()
def codec() -> MarketBoardSubsystemCodec:
    return MarketBoardSubsystemCodec()


class TestTheLastTradedPriceSurvivesASaveAndLoad:
    """品目ごとの直近の約定価格も、捕獲して復元しても残る。

    値付けの材料なので、失っても品や gold は消えない。それでも戻すのは、
    **再開のたびに相場の記憶だけが消える**世界になるため。長走 run で相場が
    育ったところで再開すると、全員が値の手がかりを同時に失う。
    """

    def test_the_price_that_cleared_comes_back(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """約定済みの品目の直近の約定価格が、復元後の板からも読める。"""
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 1)
        origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        origin._market_service.buy_best(
            _TOM, item_label=_HERB, quantity=1, current_tick=2,
        )
        spec_id = origin._item_spec_repo.find_by_name(_HERB).item_spec_id.value
        payload = json.loads(json.dumps(codec.capture(origin)))

        revived = _build(tmp_path)
        codec.restore(revived, payload)

        assert revived._market_service.board().last_trade_price_of(spec_id) == 8

    def test_a_snapshot_without_any_trade_history_still_loads(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """約定の記録が入っていない古い snapshot も、そのまま読める。

        欠落は「一度も約定していない」と同じ意味なので、拒んで再開を止める
        より読めた方がよい。**失うものが無い欠落**なので版は上げない。
        """
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 1)
        origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        payload = codec.capture(origin)
        payload.pop("last_trades", None)

        revived = _build(tmp_path)
        codec.restore(revived, payload)

        assert revived._market_service.board().last_trades == ()


class TestTheBoardSurvivesASaveAndLoad:
    """板の注文は、捕獲して復元しても同じ形で並ぶ。"""

    def test_every_order_comes_back(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """出ていた注文が、同じ ID・数量・単価で戻る。"""
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 3)
        order = origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=3, unit_price=8, current_tick=1,
        )
        payload = json.loads(json.dumps(codec.capture(origin)))

        revived = _build(tmp_path)
        codec.restore(revived, payload)

        restored = revived._market_service.board().find(order.order_id)
        assert restored is not None
        assert restored.quantity == 3
        assert restored.unit_price_gold == 8

    def test_the_expiry_is_restored_as_saved(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """期限は保存値をそのまま戻す。

        復元時に「出した手番 + 既定期間」で計算し直すと、シナリオの期間設定を
        変えた後の再開で注文の寿命が伸び縮みする。
        """
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 1)
        order = origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=7,
        )
        payload = json.loads(json.dumps(codec.capture(origin)))

        revived = _build(tmp_path)
        codec.restore(revived, payload)

        assert (
            revived._market_service.board().find(order.order_id).expires_at_tick
            == order.expires_at_tick
        )

    def test_an_order_awaiting_collection_stays_that_way(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """引き取り待ちの状態も戻る。

        戻らないと、再開のたびに期限切れの通知が届き直す。
        """
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 1)
        order = origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        inventory = origin._player_inventory_repo.find_by_id(_LENA)
        while not inventory.is_inventory_full():
            _give(origin, _LENA, _HERB, 1)
            inventory = origin._player_inventory_repo.find_by_id(_LENA)
        origin._market_service.expire_orders(current_tick=order.expires_at_tick + 1)
        payload = json.loads(json.dumps(codec.capture(origin)))

        revived = _build(tmp_path)
        codec.restore(revived, payload)

        restored = revived._market_service.board().find(order.order_id)
        assert restored.is_awaiting_collection is True

    def test_the_restored_board_can_still_be_traded_on(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """復元した板から実際に買える。

        形だけ戻って参照が切れている状態を見逃さないため。中身が一致していても
        約定できなければ、再開後の世界では板が飾りになる。
        """
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 1)
        order = origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        payload = json.loads(json.dumps(codec.capture(origin)))
        revived = _build(tmp_path)
        codec.restore(revived, payload)
        before = _gold(revived, _TOM)

        revived._market_service.take_order(
            _TOM, order_id=order.order_id, quantity=1, current_tick=2,
        )

        assert _gold(revived, _TOM) == before - 8
        assert revived._market_service.board().find(order.order_id) is None

    def test_a_new_order_after_restore_does_not_reuse_an_id(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """復元後に出した注文が、復元済みの注文と同じ ID にならない。

        ID の払い出しを戻さないと、次の出品が「同じ ID は二度置けません」で
        落ちる。再開した世界で誰も出品できなくなる。
        """
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 1)
        _give(origin, _LENA, _BREAD, 1)
        origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=8, current_tick=1,
        )
        origin._market_service.place_sell_order(
            _LENA, item_label=_BREAD, quantity=1, unit_price=9, current_tick=1,
        )
        payload = json.loads(json.dumps(codec.capture(origin)))
        revived = _build(tmp_path)
        codec.restore(revived, payload)

        fresh = revived._market_service.place_buy_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=3, current_tick=2,
        )

        assert len(revived._market_service.board().orders) == 3
        assert fresh.order_id.value == 3

    def test_an_unknown_schema_version_is_refused(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """知らない形式の payload は読み込まない (壊れた板で再開しない)。"""
        revived = _build(tmp_path)

        with pytest.raises(ValueError):
            codec.restore(revived, {"schema_version": 99, "orders": []})


class TestNothingDepositedIsLostAcrossARestart:
    """預けた品と gold が、捕獲 → 復元で消えない。"""

    def test_the_deposited_goods_can_still_be_reclaimed(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """復元した板から取り下げると、預けた品が持ち主へ戻る。"""
        origin = _build(tmp_path)
        _give(origin, _LENA, _HERB, 2)
        order = origin._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=2, unit_price=8, current_tick=1,
        )
        payload = json.loads(json.dumps(codec.capture(origin)))
        revived = _build(tmp_path)
        codec.restore(revived, payload)

        revived._market_service.cancel_order(_LENA, order_id=order.order_id)

        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            count_owned_item_instances_by_spec,
        )
        inventory = revived._player_inventory_repo.find_by_id(_LENA)
        counts = count_owned_item_instances_by_spec(inventory, revived._item_repo)
        spec_id = revived._item_spec_repo.find_by_name(_HERB).item_spec_id.value
        assert sum(c for s, c in counts.items() if s.value == spec_id) == 2

    def test_the_deposited_gold_can_still_be_reclaimed(
        self, tmp_path: Path, codec: MarketBoardSubsystemCodec
    ) -> None:
        """復元した板から買い注文を取り下げると、預けた gold が戻る。"""
        origin = _build(tmp_path)
        order = origin._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=2, unit_price=7, current_tick=1,
        )
        payload = json.loads(json.dumps(codec.capture(origin)))
        revived = _build(tmp_path)
        codec.restore(revived, payload)
        before = _gold(revived, _TOM)

        revived._market_service.cancel_order(_TOM, order_id=order.order_id)

        assert _gold(revived, _TOM) == before + 14
