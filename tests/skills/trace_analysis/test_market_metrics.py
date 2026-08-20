"""``.claude/skills/trace-analysis/market_metrics.py`` のユニットテスト。

市場 run の分析軸 (G-41〜G-48) は、**分母を持つ**ことが値そのものより重要になる。
「交差 0 件」と「交差が起こりえなかった」は分子だけ見ると区別がつかず、実際に
一度読み違えた (v3 run の分析)。このテストは、分母が出ること・分母が 0 のときに
**測定不能と分かる形**になることを見張る。

板の再現器は、実装の板そのものではない**再現**なので、既知の並びに対する
自己点検をここに固定する。今回スクラッチで書いた再現器は、この点検で
「売り注文と買い注文の値を混ぜている」バグが見つかった。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "trace-analysis" / "market_metrics.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("market_metrics", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # dataclass は自分のモジュールを ``sys.modules`` から引く。手で読み込むと
    # 登録されておらず、クラス定義の時点で落ちる (Python 3.10)。
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mm():
    return _load_module()


def _market(tick: int, event: str, **payload: Any) -> Dict[str, Any]:
    return {
        "kind": "market_activity",
        "tick": tick,
        "payload": {"market_event": event, **payload},
    }


def _listed(tick, order_id, item, side, price, qty=1, actor="トム"):
    return _market(
        tick, "listed", order_id=order_id, item_name=item, side=side,
        unit_price=price, quantity=qty, actor_name=actor,
    )


def _snapshot(tick, order_id, item, side, price, qty=1, actor="商人"):
    return _market(
        tick, "board_snapshot", order_id=order_id, item_name=item, side=side,
        unit_price=price, quantity=qty, actor_name=actor,
    )


def _action(tick: int, tool: str, *, success: bool = True, error_code=None,
            player_id: int = 1, **payload: Any) -> Dict[str, Any]:
    return {
        "kind": "action_result",
        "tick": tick,
        "player_id": player_id,
        "payload": {"tool": tool, "success": success, "error_code": error_code,
                    **payload},
    }


def _llm_call(tools: List[str]) -> Dict[str, Any]:
    return {"kind": "llm_call", "tick": 1, "payload": {"tool_names": tools}}


class TestTheBoardIsRebuiltFromTheTrace:
    """`market_activity` を順に当てて、その時点の板を復元する。"""

    def test_both_snapshot_and_listed_become_orders(self, mm) -> None:
        """初期状態 (`board_snapshot`) も出品 (`listed`) も、等しく板の注文になる。

        片方だけを見ると初期注文が丸ごと欠ける (PR #1189 で塞いだ穴)。
        """
        events = [
            _snapshot(0, 1, "パン", "sell", 20),
            _listed(5, 2, "パン", "sell", 15),
        ]

        board = mm.replay_board(events)[-1][1]

        assert {o.order_id for o in board.values()} == {1, 2}

    def test_repricing_moves_the_price_and_nothing_else(self, mm) -> None:
        """`repriced` は単価だけを変え、数量と向きは変えない。"""
        events = [
            _listed(5, 2, "パン", "sell", 15, qty=3),
            _market(8, "repriced", order_id=2, item_name="パン", side="sell",
                    unit_price=14, old_unit_price=15, quantity=3,
                    actor_name="トム"),
        ]

        order = mm.replay_board(events)[-1][1][2]

        assert (order.unit_price, order.quantity, order.side) == (14, 3, "sell")

    def test_a_partial_settlement_leaves_the_rest_on_the_board(self, mm) -> None:
        """一部だけ約定した注文は、残りの数量を持って板に残る。"""
        events = [
            _listed(5, 2, "パン", "sell", 15, qty=3),
            _market(6, "settled", resting_order_id=2, item_name="パン",
                    unit_price=15, quantity=1, taker_side="buy"),
        ]

        order = mm.replay_board(events)[-1][1][2]

        assert order.quantity == 2

    def test_a_full_settlement_removes_the_order(self, mm) -> None:
        """数量を使い切った注文は板から消える。"""
        events = [
            _listed(5, 2, "パン", "sell", 15, qty=1),
            _market(6, "settled", resting_order_id=2, item_name="パン",
                    unit_price=15, quantity=1, taker_side="buy"),
        ]

        assert mm.replay_board(events)[-1][1] == {}

    @pytest.mark.parametrize("event_name", ["cancelled", "expired"])
    def test_cancelling_and_expiring_remove_the_order(self, mm, event_name) -> None:
        """取り下げと期限切れは、どちらも注文を板から取り除く。"""
        events = [
            _listed(5, 2, "パン", "sell", 15),
            _market(9, event_name, order_id=2, item_name="パン", side="sell",
                    unit_price=15, quantity=1, actor_name="トム"),
        ]

        assert mm.replay_board(events)[-1][1] == {}

    def test_the_v3_sequence_rebuilds_into_the_board_we_saw(self, mm) -> None:
        """**自己点検**: v3 run と同じ並びを食わせると、run 中に見えた板になる。

        初期注文 (パン 24G / 20G の売り、薬草 7G の買い) に対し、薬草が 2 回
        売れて買い注文が尽き、パンの出品が 3 件増えて 1 件が 14G へ下がる。
        期待する板は run 中のプロンプト表示から手で作ったもので、**再現器の
        側を信じない**ための対照になる。
        """
        events = [
            _snapshot(0, 1, "パン", "sell", 24, actor="商人"),
            _snapshot(0, 2, "パン", "sell", 20, actor="商人"),
            _snapshot(0, 3, "薬草", "buy", 7, qty=2, actor="商人"),
            _market(8, "settled", resting_order_id=3, item_name="薬草",
                    unit_price=7, quantity=1, taker_side="sell"),
            _market(17, "settled", resting_order_id=3, item_name="薬草",
                    unit_price=7, quantity=1, taker_side="sell"),
            _listed(33, 4, "パン", "sell", 15, actor="トム"),
            _listed(35, 5, "パン", "sell", 15, actor="ノラ"),
            _market(38, "repriced", order_id=4, item_name="パン", side="sell",
                    unit_price=14, old_unit_price=15, quantity=1,
                    actor_name="トム"),
        ]

        board = mm.replay_board(events)[-1][1]

        assert sorted(
            (o.item, o.side, o.unit_price, o.quantity) for o in board.values()
        ) == [
            ("パン", "sell", 14, 1),
            ("パン", "sell", 15, 1),
            ("パン", "sell", 20, 1),
            ("パン", "sell", 24, 1),
        ]


class TestPriceSeriesKeepsTheTwoSidesApart:
    """G-41: 価格の時系列は、売りと買いを混ぜない。"""

    def test_sell_and_buy_are_separate_series(self, mm) -> None:
        """同じ品の売り最安と買い最高が、別々の系列として出る。

        混ぜると「6G の薬草と 24G のパン」が同じ線に乗って無意味になる。
        再現器を自己点検したとき、実際にここを混ぜていた。
        """
        events = [
            _listed(3, 1, "薬草", "sell", 9),
            _listed(4, 2, "薬草", "buy", 7),
        ]

        series = mm.extract_market(events)["g41_price_series"]["薬草"]

        assert series["sell"][-1][1] == 9
        assert series["buy"][-1][1] == 7

    def test_the_best_price_is_cheapest_to_buy_and_highest_to_sell(self, mm) -> None:
        """売り側は最安、買い側は最高を取る (どちらも「その人に一番良い値」)。"""
        events = [
            _listed(3, 1, "パン", "sell", 20),
            _listed(4, 2, "パン", "sell", 14),
            _listed(5, 3, "パン", "buy", 8),
            _listed(6, 4, "パン", "buy", 11),
        ]

        series = mm.extract_market(events)["g41_price_series"]["パン"]

        assert (series["sell"][-1][1], series["buy"][-1][1]) == (14, 11)


class TestItemsThatNeverReachedTheBoard:
    """G-43: 板が仲介しなかった品を、世界に現れた品を分母にして出す。"""

    def test_an_item_handled_but_never_listed_is_reported(self, mm) -> None:
        """世界で扱われたのに板に一度も載らなかった品が列挙される。

        v3 run の麦がこれ。最も需要のある品なのに出品も買い注文も 0 件で、
        **設計の主目的 (買い手同士の競争) が動いていなかった**。
        """
        events = [
            _action(4, "give_item", item_name="麦束"),
            _action(9, "market_list_item", item_name="パン"),
            _listed(9, 1, "パン", "sell", 15),
        ]

        coverage = mm.extract_market(events)["g43_item_coverage"]

        assert coverage["never_on_board"] == ["麦束"]
        assert "麦束" in coverage["seen_in_world"]


class TestItemNamesComeFromTheRequestWhenTheResultOmitsThem:
    """品名の分母を、実 trace が実際に持っている場所から取る。

    **`action_result` に `item_name` を入れているのは市場ツールだけだった。**
    合成した trace で書いたテストは全部緑だったのに、実 run に当てたら G-43 も
    G-47 も構造的に空振りしていた (対面の品名が 1 件も取れない)。品名は
    `action` の `arguments` にある。
    """

    def test_an_item_label_from_the_request_counts_as_seen(self, mm) -> None:
        """結果に品名が無くても、その呼び出しの `item_label` から品が分かる。"""
        events = [
            {"kind": "action", "tick": 4, "player_id": 1,
             "payload": {"tool": "buy_item", "arguments": {"item_label": "麦束"}}},
            _action(4, "buy_item"),
        ]

        coverage = mm.extract_market(events)["g43_item_coverage"]

        assert "麦束" in coverage["seen_in_world"]

    def test_every_item_of_a_multi_gift_is_counted(self, mm) -> None:
        """1 度に複数渡す `give_item` は、`gives` の全件から品名を取る。

        1 件目だけ見ると、まとめ渡しの品が静かに落ちる。
        """
        events = [
            {"kind": "action", "tick": 26, "player_id": 3,
             "payload": {"tool": "give_item", "arguments": {"gives": [
                 {"item_label": "パン", "target_player_label": "レナ"},
                 {"item_label": "麦束", "target_player_label": "カイ"},
             ]}}},
            _action(26, "give_item", player_id=3),
        ]

        coverage = mm.extract_market(events)["g43_item_coverage"]

        assert {"パン", "麦束"} <= set(coverage["seen_in_world"])

    def test_calls_with_no_recoverable_item_are_counted_not_dropped(self, mm) -> None:
        """どこからも品名が取れない呼び出しは、件数として残す。

        **静かに 0 件にすると「板が全部仲介した」ように見える。** 分母が
        欠けていることを、数字のそばに出す。
        """
        events = [_action(4, "give_item")]

        coverage = mm.extract_market(events)["g43_item_coverage"]

        assert coverage["unresolved_item_calls"] == 1

    def test_face_to_face_item_is_matched_against_the_board(self, mm) -> None:
        """対面の品名も `action` から取って、板に出ていたかを判定する。

        ここが取れないと G-47 の「両方選べた場面」が常に 0 になり、
        **選好の証拠が構造的に出ない**。
        """
        events = [
            _listed(5, 1, "パン", "sell", 15),
            {"kind": "action", "tick": 7, "player_id": 2,
             "payload": {"tool": "give_item", "arguments": {"gives": [
                 {"item_label": "パン", "target_player_label": "レナ"}]}}},
            _action(7, "give_item", player_id=2),
        ]

        route = mm.extract_market(events)["g47_route_choice"]

        assert route["face_to_face_while_on_board"] == 1


class TestCrossingSeparatesNeverHappenedFromCouldNotHappen:
    """G-44: 交差は、成立しうる手番数 (分母) と一緒に出す。"""

    def test_without_both_sides_the_axis_reports_itself_unmeasurable(self, mm) -> None:
        """売りと買いが同時に並んだ手番が 0 なら、**測定不能**として出る。

        ここを「交差 0 件」と書くと、次に読む人が必ず「誰も裁定に気づかなかった」
        と読む。v3 run で実際に読みかけた。
        """
        events = [_listed(3, 1, "パン", "sell", 15)]

        crossing = mm.extract_market(events)["g44_crossing"]

        assert crossing["measurable"] is False
        assert crossing["opportunity_ticks"] == 0

    def test_both_sides_present_makes_the_axis_measurable(self, mm) -> None:
        """売りと買いが並べば、交差しなくても測定可能になる。

        「機会はあったが誰も取らなかった」は、ここで初めて意味を持つ観測。
        """
        events = [
            _listed(3, 1, "パン", "sell", 15, actor="トム"),
            _listed(4, 2, "パン", "buy", 9, actor="レナ"),
        ]

        crossing = mm.extract_market(events)["g44_crossing"]

        assert crossing["measurable"] is True
        assert crossing["opportunity_ticks"] == 1
        assert crossing["crossings"] == []

    def test_a_crossed_pair_is_reported_with_its_gap(self, mm) -> None:
        """買い最高が売り最安以上になったら、品・両方の値・幅が出る。"""
        events = [
            _listed(3, 1, "パン", "sell", 12, actor="トム"),
            _listed(4, 2, "パン", "buy", 18, actor="レナ"),
        ]

        crossing = mm.extract_market(events)["g44_crossing"]["crossings"][0]

        assert (crossing["item"], crossing["ask"], crossing["bid"],
                crossing["gap"]) == ("パン", 12, 18, 6)

    def test_a_persons_own_two_orders_are_not_a_crossing(self, mm) -> None:
        """同じ人の売りと買いは交差に数えない。**自分の注文は自分で取れない**。

        数えると、1 人が両方を出しただけで「裁定機会があった」ことになる。
        """
        events = [
            _listed(3, 1, "パン", "sell", 12, actor="トム"),
            _listed(4, 2, "パン", "buy", 18, actor="トム"),
        ]

        crossing = mm.extract_market(events)["g44_crossing"]

        assert crossing["crossings"] == []
        assert crossing["opportunity_ticks"] == 0


class TestRouteChoiceCountsOnlyContestedMoments:
    """G-47: 経路の選択は、両方選べた場面だけが選好の証拠になる。"""

    def test_face_to_face_while_the_board_had_the_same_item(self, mm) -> None:
        """対面が選ばれた回数のうち、同じ品が板にも出ていた回数が分かれる。

        板が空なら対面を選ぶのは当たり前で、選好の証拠にならない。
        """
        events = [
            _action(2, "give_item", item_name="パン"),
            _listed(5, 1, "パン", "sell", 15),
            _action(7, "give_item", item_name="パン"),
        ]

        route = mm.extract_market(events)["g47_route_choice"]

        assert route["face_to_face_calls"] == 2
        assert route["face_to_face_while_on_board"] == 1


class TestToolsThatWereOfferedButNeverCalled:
    """G-48: 0 回のツールは失敗分布に一行も出ない。専用に見る。"""

    def test_an_exposed_but_unused_market_tool_is_listed(self, mm) -> None:
        """LLM に出ていたのに 1 度も呼ばれなかった市場ツールが列挙される。

        分母は trace の `llm_call.tool_names` (= 実際に出ていたツール)。
        シナリオが落としたツールを「使われなかった」と数えないため。
        """
        events = [
            _llm_call(["market_list_item", "market_buy", "travel_to"]),
            _action(9, "market_list_item", item_name="パン"),
        ]

        exposure = mm.extract_market(events)["g48_tool_exposure"]

        assert exposure["never_called"] == ["market_buy"]

    def test_a_tool_that_was_never_offered_is_not_counted_as_unused(self, mm) -> None:
        """出ていなかったツールは「使われなかった」に入らない (**正の対照**)。"""
        events = [
            _llm_call(["market_list_item"]),
            _action(9, "market_list_item", item_name="パン"),
        ]

        exposure = mm.extract_market(events)["g48_tool_exposure"]

        assert exposure["never_called"] == []

    def test_unused_tools_do_not_appear_among_failures(self, mm) -> None:
        """0 回のツールは error_code 分布に現れない。

        失敗していないので当然だが、**だからこそ既存の失敗軸では見えない**。
        この対照が、G-48 を別軸にした理由そのもの。
        """
        events = [
            _llm_call(["market_list_item", "market_buy"]),
            _action(9, "market_list_item", success=False,
                    error_code="INVENTORY_FULL", item_name="パン"),
        ]

        exposure = mm.extract_market(events)["g48_tool_exposure"]

        assert "market_buy" in exposure["never_called"]
        assert "market_buy" not in exposure["error_codes"]


class TestARunWithoutAMarketSaysSo:
    """市場のない run では、軸そのものが測定不能だと分かる。"""

    def test_no_market_activity_makes_the_whole_section_unmeasurable(self, mm) -> None:
        """`market_activity` が 1 件も無い run は `measurable: false` になる。

        0 が並んだ表を「市場が使われなかった」と読ませないため。
        """
        events = [_action(3, "travel_to"), _llm_call(["travel_to"])]

        assert mm.extract_market(events)["measurable"] is False
