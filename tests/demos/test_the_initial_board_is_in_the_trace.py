"""板の初期状態が trace に残り、trace だけで板を復元できる。

初期注文は `create_world_runtime` の中で置かれ、`set_trace_recorder` はその
あとに呼ばれる。**recorder がまだ無いので、初期注文は 1 行も記録されなかった。**

実 run (`market_town_v3_first`) で実際に困った。板には確かに載っていて
(プロンプトに「20G で買える (出品 2件)」が出ていて、薬草の約定もその買い注文に
当たっている) のに、`market_activity` の `listed` はエージェントの 3 件だけ。
trace だけから板を復元すると初期注文が丸ごと欠け、それを指す `settled` を
**復元器が黙って読み飛ばす**。

`docs/trace_format.md` に「価格の時系列が引ける」と書いた以上、**trace だけで
完結**していなければ半分嘘になる。

初期状態は `listed` では流さない。同じ kind にすると、分析側が「t0 に全員が
同時に出品した」と読む。**スナップショットと分かる形** (`board_snapshot`) で残す。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"

_INITIAL_ORDERS = [
    {"merchant": "gustav", "side": "sell", "item_spec": "bread",
     "quantity": 1, "unit_price": 24},
    {"merchant": "gustav", "side": "sell", "item_spec": "bread",
     "quantity": 1, "unit_price": 20},
    {"merchant": "gustav", "side": "buy", "item_spec": "herb",
     "quantity": 2, "unit_price": 7},
]


class _Recorder:
    """記録された trace をそのまま覚えておくだけの recorder。"""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []

    def record(self, kind, **payload) -> None:
        self.records.append({"kind": str(getattr(kind, "value", kind)), **payload})


def _build(tmp_path: Path, *, with_orders: bool = True) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["market"] = {
        "board_spot": "market_square",
        "initial_orders": _INITIAL_ORDERS if with_orders else [],
    }
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _snapshot_rows(recorder: _Recorder) -> List[Dict[str, Any]]:
    return [
        r for r in recorder.records
        if r["kind"] == "market_activity" and r.get("market_event") == "board_snapshot"
    ]


class TestTheBoardIsWrittenDownWhenTheRecorderArrives:
    """recorder が付いた時点で、板の現状が 1 行ずつ残る。"""

    def test_every_standing_order_is_recorded(self, tmp_path: Path) -> None:
        """板に出ている注文が、すべて記録される。"""
        runtime = _build(tmp_path)
        recorder = _Recorder()

        runtime.set_trace_recorder(recorder)

        assert len(_snapshot_rows(recorder)) == len(_INITIAL_ORDERS)

    def test_each_row_carries_what_the_board_shows(self, tmp_path: Path) -> None:
        """各行が、品目・向き・数量・単価を持つ。

        これが無いと復元できない。**「初期注文があった」だけでは板は戻らない。**
        """
        runtime = _build(tmp_path)
        recorder = _Recorder()

        runtime.set_trace_recorder(recorder)

        rows = _snapshot_rows(recorder)
        assert {(r["side"], r["unit_price"], r["quantity"]) for r in rows} == {
            (o["side"], o["unit_price"], o["quantity"]) for o in _INITIAL_ORDERS
        }

    def test_the_rows_are_not_disguised_as_listings(self, tmp_path: Path) -> None:
        """初期状態を `listed` として流さない。

        同じ kind にすると、分析側が**「その手番に全員が同時に出品した」**と
        読む。出品は出来事だが、スナップショットは出来事ではない。
        """
        runtime = _build(tmp_path)
        recorder = _Recorder()

        runtime.set_trace_recorder(recorder)

        listed = [
            r for r in recorder.records
            if r["kind"] == "market_activity" and r.get("market_event") == "listed"
        ]
        assert listed == []

    def test_an_empty_board_records_nothing(self, tmp_path: Path) -> None:
        """初期注文の無い世界では 1 行も出ない (**正の対照**)。

        毎回スナップショットが出ると、板の無い世界の trace が太る。
        """
        runtime = _build(tmp_path, with_orders=False)
        recorder = _Recorder()

        runtime.set_trace_recorder(recorder)

        assert _snapshot_rows(recorder) == []


class TestTheBoardCanBeRebuiltFromTheTraceAlone:
    """trace だけで板を復元でき、シナリオ宣言と一致する。

    **今回、私が手でシナリオから補った作業を、機械が代わりにやる形にする。**
    補わないと復元できない状態のままだと、次に分析する人が同じ穴に落ちる。
    """

    def test_the_rebuilt_board_matches_the_declaration(self, tmp_path: Path) -> None:
        """復元した板が、シナリオに書いた初期注文と一致する。"""
        runtime = _build(tmp_path)
        recorder = _Recorder()
        runtime.set_trace_recorder(recorder)

        rebuilt = _rebuild_board(recorder.records)

        assert sorted(rebuilt) == sorted(
            (o["side"], o["unit_price"], o["quantity"]) for o in _INITIAL_ORDERS
        )

    def test_a_settlement_can_be_traced_back_to_its_order(self, tmp_path: Path) -> None:
        """約定が、復元した板の注文に辿れる。

        **これが欠けていたもの。** 実 run では、初期注文への約定が
        「`listed` の無い注文への `settled`」になり、復元器が黙って読み飛ばした。
        """
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        runtime = _build(tmp_path)
        recorder = _Recorder()
        runtime.set_trace_recorder(recorder)
        lena = PlayerId(1)
        herb = runtime._item_spec_repo.find_by_name("薬草").item_spec_id.value
        grant_item_specs_to_inventory(
            lena, (ItemSpecId.create(herb),), runtime._item_repo,
            runtime._item_spec_repo, runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )

        runtime._market_service.sell_best(
            lena, item_label="薬草", quantity=1, current_tick=runtime.current_tick(),
        )

        known = _known_order_ids(recorder.records)
        settled = [
            r for r in recorder.records
            if r["kind"] == "market_activity" and r.get("market_event") == "settled"
        ]
        assert len(settled) == 1
        assert settled[0]["resting_order_id"] in known, (
            "約定が、trace にある注文へ辿れない (初期注文が記録されていない)"
        )


def _known_order_ids(records: List[Dict[str, Any]]) -> set:
    """trace に現れた注文 ID (スナップショットと出品の両方から)。"""
    return {
        r["order_id"]
        for r in records
        if r["kind"] == "market_activity"
        and r.get("market_event") in ("board_snapshot", "listed")
        and r.get("order_id") is not None
    }


def _rebuild_board(records: List[Dict[str, Any]]) -> List[tuple]:
    """trace だけで板を復元する (分析側がやる作業の最小版)。"""
    orders: Dict[int, tuple] = {}
    for r in records:
        if r["kind"] != "market_activity":
            continue
        event, oid = r.get("market_event"), r.get("order_id")
        if event in ("board_snapshot", "listed") and oid is not None:
            orders[oid] = (r["side"], r["unit_price"], r["quantity"])
        elif event in ("cancelled", "expired"):
            orders.pop(oid, None)
    return list(orders.values())
