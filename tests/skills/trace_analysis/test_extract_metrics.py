"""``.claude/skills/trace-analysis/extract_metrics.py`` のユニットテスト。

trace-analysis SKILL の核となる指標抽出スクリプトが、想定する trace 構造から
正しい数値を取り出せることを保証する。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "trace-analysis" / "extract_metrics.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_metrics", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def em():
    return _load_module()


def _write_trace(tmp_path: Path, events: list[dict]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with (run_dir / "trace.jsonl").open("w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return run_dir


class TestSummary:
    def test_aggregates_llm_call_latency_token(self, em, tmp_path) -> None:
        """llm_call 3 件 / cached_tokens 入りで cache hit 率も出る。"""
        events = [
            {"kind": "llm_call", "tick": 1, "player_id": 1, "payload": {
                "wall_latency_ms": 1000, "prompt_tokens": 100, "cached_tokens": 50,
                "completion_tokens": 10, "cost_usd": 0.001,
            }},
            {"kind": "llm_call", "tick": 2, "player_id": 1, "payload": {
                "wall_latency_ms": 2000, "prompt_tokens": 200, "cached_tokens": 100,
                "completion_tokens": 20, "cost_usd": 0.002,
            }},
            {"kind": "llm_call", "tick": 3, "player_id": 2, "payload": {
                "wall_latency_ms": 3000, "prompt_tokens": 300, "cached_tokens": 200,
                "completion_tokens": 30, "cost_usd": 0.003,
            }},
        ]
        m = em.compute_metrics(_write_trace(tmp_path, events))
        s = m["summary"]
        assert s["llm_calls"] == 3
        assert s["prompt_tokens_total"] == 600
        assert s["cached_tokens_total"] == 350
        assert s["completion_tokens_total"] == 60
        assert s["cache_hit_ratio"] == pytest.approx(350 / 600)
        assert s["cost_usd_total"] == pytest.approx(0.006)
        # latency は p50 = 中央 = 2 秒 (n=3 の middle index)
        assert s["latency_p50_s"] == pytest.approx(2.0)

    def test_failure_action_result_success_false_ratio(self, em, tmp_path) -> None:
        """失敗率は actionresult の successFalse の比率。"""
        events = [
            {"kind": "action_result", "payload": {"success": True}},
            {"kind": "action_result", "payload": {"success": False, "error_code": "X"}},
            {"kind": "action_result", "payload": {"success": False, "error_code": "Y"}},
            {"kind": "action_result", "payload": {"success": True}},
        ]
        m = em.compute_metrics(_write_trace(tmp_path, events))
        assert m["summary"]["action_total"] == 4
        assert m["summary"]["action_fail"] == 2
        assert m["summary"]["action_fail_rate"] == pytest.approx(0.5)


class TestPerPlayer:
    def test_player_different_tool_histogram_failure_error_code(self, em, tmp_path) -> None:
        """player 別 toolhistogram と失敗 errorcode 集計。"""
        events = [
            {"kind": "action", "tick": 1, "player_id": 1, "payload": {
                "tool": "explore", "arguments": {},
            }},
            {"kind": "action_result", "payload": {
                "tool": "explore", "success": True,
            }},
            {"kind": "action", "tick": 2, "player_id": 1, "payload": {
                "tool": "travel_to", "arguments": {},
            }},
            {"kind": "action_result", "payload": {
                "tool": "travel_to", "success": False,
                "error_code": "INVALID_DESTINATION_LABEL",
            }},
            {"kind": "llm_call", "tick": 1, "player_id": 1, "payload": {}},
            {"kind": "llm_call", "tick": 1, "player_id": 2, "payload": {}},
        ]
        m = em.compute_metrics(_write_trace(tmp_path, events))
        assert m["per_player"]["P1"]["tool_histogram"] == {
            "explore": 1, "travel_to": 1,
        }
        assert m["per_player"]["P1"]["error_code_distribution"] == {
            "INVALID_DESTINATION_LABEL": 1,
        }
        assert m["per_player"]["P1"]["llm_calls"] == 1
        assert m["per_player"]["P2"]["llm_calls"] == 1


class TestPerTool:
    def test_tool_different_success_failure_error_code_breakdown(self, em, tmp_path) -> None:
        """tool 別 成功 失敗 error code breakdown。"""
        events = [
            {"kind": "action_result", "payload": {
                "tool": "use_item", "success": False, "error_code": "ITEM_NOT_CONSUMABLE",
            }},
            {"kind": "action_result", "payload": {
                "tool": "use_item", "success": False, "error_code": "ITEM_NOT_CONSUMABLE",
            }},
            {"kind": "action_result", "payload": {"tool": "use_item", "success": True}},
        ]
        m = em.compute_metrics(_write_trace(tmp_path, events))
        rows = m["per_tool"]
        u = next(r for r in rows if r["tool"] == "use_item")
        assert u["total"] == 3
        assert u["success"] == 1
        assert u["fail"] == 2
        assert u["error_codes"] == {"ITEM_NOT_CONSUMABLE": 2}


class TestIssue621Chain:
    def test_counts_player_downed_event_tend_player(self, em, tmp_path) -> None:
        """PlayerDownedEvent と tendtoplayer を数える。"""
        events = [
            {"kind": "observation", "payload": {"prose": "PlayerDownedEvent fired"}},
            {"kind": "action", "payload": {"tool": "tend_to_player"}},
            {"kind": "action_result", "payload": {"tool": "tend_to_player", "success": True}},
        ]
        chain = em.compute_metrics(_write_trace(tmp_path, events))["issue621_chain"]
        assert chain["PlayerDownedEvent"] >= 1
        assert chain["tend_to_player"] >= 1

    def test_counts_down_structured_player_downed(self, em, tmp_path) -> None:
        """実 trace の down は文字列 "PlayerDownedEvent" ではなく observation の
        structured.type=="player_downed" で表現される。self 視点 (role=="self") が
        実際の down 1 件、social 視点は他プレイヤーの観測。

        現抽出器は "PlayerDownedEvent" 文字列だけを数えるため、実 run の down を
        取り逃がして 0 と出していた (v3coop_stagnation_002 で P3/P4 が down したのに
        PlayerDownedEvent=0)。structured 由来の実カウントを別途出す。
        """
        events = [
            # 実 down (自分視点)
            {"kind": "observation", "player_id": 3, "payload": {
                "structured": {"type": "player_downed", "role": "self"}}},
            # 他プレイヤーが観測した social な player_downed (実 down ではない)
            {"kind": "observation", "player_id": 1, "payload": {
                "structured": {"type": "player_downed", "actor": "リオ"}}},
            {"kind": "observation", "player_id": 2, "payload": {
                "structured": {"type": "player_downed", "actor": "リオ"}}},
        ]
        chain = em.compute_metrics(_write_trace(tmp_path, events))["issue621_chain"]
        # 実際の down は self 視点の 1 件
        assert chain["player_downed_self"] == 1
        # self+social すべての player_downed observation は 3 件
        assert chain["player_downed_observations"] == 3


class TestComparison:
    def test_baseline_line_created(self, em, tmp_path) -> None:
        """baseline を渡すと比較行が生成される。"""
        ev1 = [{"kind": "llm_call", "payload": {"wall_latency_ms": 1000, "prompt_tokens": 100, "cached_tokens": 50}}]
        ev2 = [{"kind": "llm_call", "payload": {"wall_latency_ms": 2000, "prompt_tokens": 100, "cached_tokens": 50}}]
        run = _write_trace(tmp_path, ev1)
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        with (base_dir / "trace.jsonl").open("w") as f:
            for e in ev2:
                f.write(json.dumps(e) + "\n")

        cur = em.compute_metrics(run)
        base = em.compute_metrics(base_dir)
        rows = em._make_comparison(cur, base)
        assert any(r["label"] == "LLM 呼び出し数" for r in rows)
        llm_row = next(r for r in rows if r["label"] == "LLM 呼び出し数")
        assert llm_row["current"] == 1 and llm_row["baseline"] == 1


class TestSurvivalProgress:
    """P1: survival 系 run の中間到達指標を trace から拾う。"""

    def _pos(self, tick, pid, spot, name="?"):
        return {
            "kind": "position_change",
            "tick": tick,
            "player_id": pid,
            "payload": {"to_spot_id": str(tick), "spot_name": spot, "player_name": name},
        }

    def test_summit_reached_records_first_arrival_per_player(self, em) -> None:
        events = [
            self._pos(10, 1, "難破船の浜"),
            self._pos(50, 1, "山頂"),
            self._pos(60, 1, "山頂"),  # 2 度目は無視
            self._pos(80, 2, "山頂"),
        ]
        out = em._extract_survival_progress(events)
        assert out["summit_reached"]["P1"]["tick"] == 50
        assert out["summit_reached"]["P2"]["tick"] == 80

    def test_summit_when_never_reached(self, em) -> None:
        out = em._extract_survival_progress([self._pos(10, 1, "難破船の浜")])
        assert out["summit_reached"] == {}

    def test_signal_fire_detected_from_success_message(self, em) -> None:
        """狼煙点火は点火 interaction の成功メッセージで検出する (失敗は無視)。"""
        events = [
            {
                "kind": "action_result", "tick": 40,
                "payload": {"tool": "spot_graph_interact", "success": False,
                            "result_summary": "火種の枯れ葉が必要だ。"},
            },
            {
                "kind": "action_result", "tick": 70,
                "payload": {"tool": "spot_graph_interact", "success": True,
                            "result_summary": "流木に火が回った。狼煙台から白い煙が立ち上る。"},
            },
        ]
        out = em._extract_survival_progress(events)
        assert out["signal_fire_lit_tick"] == 70

    def test_signal_fire_None_when_lit(self, em) -> None:
        events = [
            {"kind": "action_result", "tick": 10,
             "payload": {"tool": "spot_graph_interact", "success": True,
                         "result_summary": "乾いた流木を拾い上げた。"}},
        ]
        assert em._extract_survival_progress(events)["signal_fire_lit_tick"] is None

    def test_first_visit_timeline_is_global_first_per_spot(self, em) -> None:
        events = [
            self._pos(10, 1, "難破船の浜"),
            self._pos(20, 2, "難破船の浜"),  # 2 人目の同スポットは初訪問に数えない
            self._pos(30, 2, "森の奥"),
        ]
        out = em._extract_survival_progress(events)
        assert out["distinct_spots_visited"] == 2
        assert out["spots_visited"] == ["森の奥", "難破船の浜"]
        visits = {r["spot_name"]: r["tick"] for r in out["spot_first_visits"]}
        assert visits == {"難破船の浜": 10, "森の奥": 30}
        # 時系列は tick 昇順。
        assert [r["tick"] for r in out["spot_first_visits"]] == [10, 30]

    def test_landmark_first_visit_tick(self, em) -> None:
        events = [
            self._pos(15, 1, "大樫の樹"),
            self._pos(25, 1, "崖の見張り台"),
        ]
        out = em._extract_survival_progress(events)
        assert out["landmark_first_visit_tick"]["大樫"] == 15
        assert out["landmark_first_visit_tick"]["見張り台"] == 25
        assert out["landmark_first_visit_tick"]["山頂"] is None

    def test_scenario_name_from_run_start(self, em) -> None:
        events = [
            {"kind": "run_start", "payload": {"scenario": "survival_island_v2_short"}},
            self._pos(10, 1, "難破船の浜"),
        ]
        assert em._extract_survival_progress(events)["scenario"] == "survival_island_v2_short"

    def test_included_in_compute_metrics(self, em, tmp_path) -> None:
        run = _write_trace(tmp_path, [self._pos(50, 1, "山頂")])
        metrics = em.compute_metrics(run)
        assert "survival_progress" in metrics
        assert metrics["survival_progress"]["summit_reached"]["P1"]["tick"] == 50


class TestCoopCopresence:
    """PR-A: 協力シナリオ v3_coop の勝敗判別指標 — ペア別 / 全員同スポット共在。"""

    def _tick_start(self, tick):
        return {"kind": "tick_start", "tick": tick, "payload": {}}

    def _pos(self, tick, pid, spot, name):
        return {
            "kind": "position_change",
            "tick": tick,
            "player_id": pid,
            "payload": {"to_spot_id": spot, "spot_name": spot, "player_name": name},
        }

    def test_counts_same_spot_tick(self, em) -> None:
        """P1 は tick0-2 で浜、P2 は tick0-1 で浜・tick2 で森 → 共在は tick0-1 の 2。"""
        events = [
            self._tick_start(0), self._tick_start(1), self._tick_start(2),
            self._pos(0, 1, "浜", "エイダ"),
            self._pos(0, 2, "浜", "ノア"),
            self._pos(2, 2, "森", "ノア"),
        ]
        out = em._extract_coop_copresence(events)
        assert out["pair_copresence_ticks"]["P1-P2"] == 2
        assert out["tick_count"] == 3

    def test_player_before_spot_id_carry_forward(self, em) -> None:
        """position_change が起きない tick は「最後に移動した先」に居続けたとみなす。"""
        events = [
            self._tick_start(0), self._tick_start(1), self._tick_start(2),
            self._tick_start(3), self._tick_start(4),
            self._pos(0, 1, "浜", "エイダ"),
            self._pos(0, 2, "浜", "ノア"),
            self._pos(3, 1, "森", "エイダ"),
        ]
        out = em._extract_coop_copresence(events)
        # tick0-2 は P1/P2 とも浜 (3), tick3-4 は P1=森/P2=浜 (共在なし)。
        assert out["pair_copresence_ticks"]["P1-P2"] == 3

    def test_counts_all_players_spot_tick(self, em) -> None:
        """全員同スポットの tick 数を 数える。"""
        events = [
            self._tick_start(0), self._tick_start(1),
            self._pos(0, 1, "浜", "エイダ"),
            self._pos(0, 2, "浜", "ノア"),
            self._pos(0, 3, "浜", "カイ"),
            self._pos(1, 3, "森", "カイ"),
        ]
        out = em._extract_coop_copresence(events)
        assert out["all_players_copresence_ticks"] == 1

    def test_position_change_player(self, em) -> None:
        """観測されていない player の位置は不明として扱い、過大集計しない。"""
        events = [
            self._tick_start(0),
            self._pos(0, 1, "浜", "エイダ"),
            {"kind": "llm_call", "tick": 0, "player_id": 4, "payload": {}},
        ]
        out = em._extract_coop_copresence(events)
        assert out["player_ids"] == [1]
        assert out["pair_copresence_ticks"] == {}

    def test_preserves_player_name(self, em) -> None:
        """playername を保持する。"""
        events = [self._tick_start(0), self._pos(0, 1, "浜", "エイダ")]
        out = em._extract_coop_copresence(events)
        assert out["player_names"]["P1"] == "エイダ"

    def test_returns_empty_when_all_zero(self, em) -> None:
        """イベントが空なら 全て 0 で返す。"""
        out = em._extract_coop_copresence([])
        assert out == {
            "player_ids": [],
            "player_names": {},
            "tick_count": 0,
            "pair_copresence_ticks": {},
            "all_players_copresence_ticks": 0,
        }


class TestHearsayEvidenceBySpeaker:
    """PR-A: belief_evidence (source_kind=hearsay) の話者別集計。"""

    def _hearsay(self, speaker):
        return {
            "kind": "belief_evidence",
            "payload": {"source_kind": "hearsay", "source_speaker": speaker},
        }

    def test_hearsay_source_kind(self, em) -> None:
        """hearsay 以外の sourcekind は数えない。"""
        events = [
            self._hearsay("リオ"),
            {"kind": "belief_evidence", "payload": {"source_kind": "prediction_error"}},
        ]
        out = em._extract_hearsay_evidence_by_speaker(events)
        assert out["total"] == 1
        assert out["by_speaker"] == {"リオ": 1}

    def test_speaker_count(self, em) -> None:
        """話者別に 件数を 積む。"""
        events = [self._hearsay("リオ"), self._hearsay("リオ"), self._hearsay("ノア")]
        out = em._extract_hearsay_evidence_by_speaker(events)
        assert out["total"] == 3
        assert out["by_speaker"] == {"リオ": 2, "ノア": 1}


class TestPendingPredictionVerdicts:
    """PR-A: 約束 (pending_prediction_*) の kind 別件数と resolved の verdict 内訳。

    将来 pending_prediction_verdict_rejected のような未知 kind が増える想定
    のため、既知 3 種以外の suffix も拾えることを確認する。
    """

    def test_counts_created_resolved_expired_count(self, em) -> None:
        """createdresolvedexpired の件数を数える。"""
        events = [
            {"kind": "pending_prediction_created", "payload": {}},
            {"kind": "pending_prediction_created", "payload": {}},
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "fulfilled"}},
            {"kind": "pending_prediction_expired", "payload": {}},
        ]
        out = em._extract_pending_prediction_verdicts(events)
        assert out["by_kind"] == {"created": 2, "resolved": 1, "expired": 1}

    def test_resolved_verdict_breakdown(self, em) -> None:
        """resolved を verdict 別に 内訳する。"""
        events = [
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "fulfilled"}},
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "fulfilled"}},
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "broken"}},
        ]
        out = em._extract_pending_prediction_verdicts(events)
        assert out["resolved_verdict_breakdown"] == {"fulfilled": 2, "broken": 1}

    def test_unknown_pending_prediction_kind_included(self, em) -> None:
        """未知の pendingpredictionkind も bykind に乗る。"""
        events = [{"kind": "pending_prediction_verdict_rejected", "payload": {}}]
        out = em._extract_pending_prediction_verdicts(events)
        assert out["by_kind"] == {"verdict_rejected": 1}


class TestGiveItem:
    """PR-A: give_item の action_result を成功/失敗別に数える。"""

    def test_counts_give_item_success_failure(self, em) -> None:
        """giveitem の成功失敗を数える。"""
        events = [
            {"kind": "action_result", "payload": {"tool": "give_item", "success": True}},
            {"kind": "action_result", "payload": {"tool": "give_item", "success": False}},
            {"kind": "action_result", "payload": {"tool": "travel_to", "success": True}},
        ]
        out = em._extract_give_item(events)
        assert out == {"total": 2, "success": 1, "fail": 1}

    def test_give_item_all_zero(self, em) -> None:
        """giveitem が一件も無ければ全て 0。"""
        out = em._extract_give_item([])
        assert out == {"total": 0, "success": 0, "fail": 0}


class TestCoopMetricsIncludedInComputeMetrics:
    def test_compute_metrics_included(self, em, tmp_path) -> None:
        """computemetrics に新指標が含まれる。"""
        events = [
            {"kind": "tick_start", "tick": 0, "payload": {}},
            {
                "kind": "position_change", "tick": 0, "player_id": 1,
                "payload": {"to_spot_id": "浜", "spot_name": "浜", "player_name": "エイダ"},
            },
            {
                "kind": "belief_evidence",
                "payload": {"source_kind": "hearsay", "source_speaker": "リオ"},
            },
            {"kind": "pending_prediction_created", "payload": {}},
            {"kind": "action_result", "payload": {"tool": "give_item", "success": True}},
        ]
        m = em.compute_metrics(_write_trace(tmp_path, events))
        assert m["coop_copresence"]["player_names"]["P1"] == "エイダ"
        assert m["coop_hearsay_by_speaker"]["by_speaker"] == {"リオ": 1}
        assert m["coop_pending_prediction"]["by_kind"] == {"created": 1}
        assert m["coop_give_item"]["success"] == 1


def _action(tick: int, pid: int, tool: str) -> dict:
    return {"kind": "action", "tick": tick, "player_id": pid, "payload": {"tool": tool}}


class TestActionBudget:
    """_extract_action_budget が行動を用途別に束ね、世界を変える行動の割合を出す挙動を保証する。"""

    def test_categorises_tools_and_computes_shares(self, em) -> None:
        """speak/memo_add/travel_to/explore/interact を 1 件ずつ渡すと、各カテゴリ 1 件・
        世界を変える行動 (移動 + 探索 + 世界操作) が 5 件中 3 件で 60.0% になる。"""
        events = [
            _action(0, 1, "speak"),
            _action(1, 1, "memo_add"),
            _action(2, 1, "travel_to"),
            _action(3, 1, "explore"),
            _action(4, 1, "interact"),
        ]
        out = em._extract_action_budget(events)
        assert out["total_actions"] == 5
        assert out["per_category"] == {
            "conversation": 1,
            "memo": 1,
            "movement": 1,
            "exploration": 1,
            "world_change": 1,
        }
        assert out["world_changing_actions"] == 3
        assert out["world_changing_share"] == 60.0

    def test_conversation_includes_listen_and_recall_excluded_from_world_change(
        self, em
    ) -> None:
        """listen は会話に、memory_recall_episodes は想起に入り、どちらも
        世界を変える行動には数えない (= 世界を変える行動 0 件で 0.0%)。"""
        events = [
            _action(0, 1, "listen"),
            _action(1, 1, "memory_recall_episodes"),
        ]
        out = em._extract_action_budget(events)
        assert out["per_category"] == {"conversation": 1, "recall": 1}
        assert out["world_changing_share"] == 0.0

    def test_unknown_tool_is_surfaced_as_unclassified_with_its_real_name(
        self, em
    ) -> None:
        """分類表に無いツールは総数から消えず、unclassified として実名と件数が残る。"""
        events = [_action(0, 1, "speak"), _action(1, 1, "brand_new_tool")]
        out = em._extract_action_budget(events)
        assert out["total_actions"] == 2
        assert out["per_category"]["unclassified"] == 1
        assert out["unclassified_tools"] == {"brand_new_tool": 1}

    def test_no_tool_is_classified_into_two_categories(self, em) -> None:
        """同じツールを 2 つのカテゴリに入れると割合の分母が壊れるため、
        ACTION_BUDGET_CATEGORIES の全ツールは重複なく 1 カテゴリだけに属する。"""
        seen: dict[str, str] = {}
        for category, tools in em.ACTION_BUDGET_CATEGORIES.items():
            for tool in tools:
                assert tool not in seen, (
                    f"{tool} が {seen.get(tool)} と {category} の両方に入っている"
                )
                seen[tool] = category

    def test_per_player_share_is_relative_to_that_player(self, em) -> None:
        """割合は player ごとの総数で正規化する。P1 が speak 2 件・travel_to 2 件なら
        会話 50.0% で、他 player の件数には影響されない。"""
        events = [
            _action(0, 1, "speak"),
            _action(1, 1, "speak"),
            _action(2, 1, "travel_to"),
            _action(3, 1, "travel_to"),
            _action(4, 2, "speak"),
        ]
        out = em._extract_action_budget(events)
        assert out["per_player_share"]["1"]["conversation"] == 50.0
        assert out["per_player_share"]["2"]["conversation"] == 100.0

    def test_empty_trace_returns_zero_share_without_dividing_by_zero(self, em) -> None:
        """action が 1 件も無い trace でも例外を投げず、割合は 0.0 を返す。"""
        out = em._extract_action_budget([])
        assert out["total_actions"] == 0
        assert out["world_changing_share"] == 0.0


class TestSpeakChains:
    """_extract_speak_chains が speak の直後の行動と speak 連鎖の長さを出す挙動を保証する。"""

    def test_counts_speak_to_speak_share(self, em) -> None:
        """P1 が speak→speak→travel_to のとき、後続を持つ speak 2 件のうち
        1 件が speak なので speak→speak は 50.0%。"""
        events = [
            _action(0, 1, "speak"),
            _action(1, 1, "speak"),
            _action(2, 1, "travel_to"),
        ]
        out = em._extract_speak_chains(events)
        assert out["speak_with_following_action"] == 2
        assert out["speak_to_speak"] == 1
        assert out["speak_to_speak_share"] == 50.0
        assert out["next_action_after_speak"] == {"speak": 1, "travel_to": 1}

    def test_trailing_speak_has_no_following_action(self, em) -> None:
        """列の最後の speak は「直後の行動」を持たないため分母に入れない。
        speak 1 件だけの trace では分母 0 で 0.0% を返す。"""
        out = em._extract_speak_chains([_action(0, 1, "speak")])
        assert out["speak_with_following_action"] == 0
        assert out["speak_to_speak_share"] == 0.0

    def test_chains_do_not_cross_players(self, em) -> None:
        """別 player の speak は連鎖として繋げない。P1 と P2 が交互に speak しても
        最長連続はそれぞれ 1 に留まる。"""
        events = [
            _action(0, 1, "speak"),
            _action(0, 2, "speak"),
            _action(1, 1, "travel_to"),
            _action(1, 2, "travel_to"),
        ]
        out = em._extract_speak_chains(events)
        assert out["longest_consecutive_speak_per_player"] == {"1": 1, "2": 1}
        assert out["speak_to_speak"] == 0

    def test_longest_run_resets_after_other_action(self, em) -> None:
        """speak が他の行動で中断されると連続数は 0 に戻る。
        speak→speak→explore→speak なら最長は 2。"""
        events = [
            _action(0, 1, "speak"),
            _action(1, 1, "speak"),
            _action(2, 1, "explore"),
            _action(3, 1, "speak"),
        ]
        out = em._extract_speak_chains(events)
        assert out["longest_consecutive_speak_per_player"]["1"] == 2


class TestSpatialDispersion:
    """_extract_spatial_dispersion が tick ごとの分散度と死亡前の切り分けを出す挙動を保証する。"""

    def _tick(self, tick: int) -> dict:
        return {"kind": "tick_start", "tick": tick, "payload": {}}

    def _pos(self, tick: int, pid: int, spot: str) -> dict:
        return {
            "kind": "position_change",
            "tick": tick,
            "player_id": pid,
            "payload": {"to_spot_id": spot, "spot_name": spot, "player_name": f"P{pid}"},
        }

    def _death(self, tick: int, pid: int, outcome: str = "DEAD") -> dict:
        return {
            "kind": "observation",
            "tick": tick,
            "player_id": pid,
            "payload": {
                "prose": "死亡した。",
                "structured": {
                    "type": "player_outcome_resolved",
                    "player_id": pid,
                    "old_outcome": "UNRESOLVED",
                    "new_outcome": outcome,
                },
            },
        }

    def test_all_together_gives_mean_one(self, em) -> None:
        """全 tick で 2 人が同じスポットにいると、分散は毎 tick 1 箇所で平均 1.0。"""
        events = [
            self._tick(0), self._tick(1),
            self._pos(0, 1, "浜"), self._pos(0, 2, "浜"),
        ]
        out = em._extract_spatial_dispersion(events)
        assert out["mean_distinct_spots"] == 1.0
        assert out["distinct_spot_histogram"] == {"1": 2}

    def test_split_raises_mean_and_is_carried_forward(self, em) -> None:
        """tick1 で P2 が森へ移ると tick1 以降は 2 箇所になる。移動しない tick も
        直前のスポットに居続けたとみなすので、3 tick の平均は (1+2+2)/3 = 1.67。"""
        events = [
            self._tick(0), self._tick(1), self._tick(2),
            self._pos(0, 1, "浜"), self._pos(0, 2, "浜"),
            self._pos(1, 2, "森"),
        ]
        out = em._extract_spatial_dispersion(events)
        assert out["distinct_spot_histogram"] == {"1": 1, "2": 2}
        assert out["mean_distinct_spots"] == 1.67

    def test_before_first_death_excludes_ticks_from_the_death_onward(self, em) -> None:
        """死体の位置が carry-forward で分散を膨らませるため、最初の死亡 tick 以降を
        除いた値も返す。tick2 で死亡なら死亡前は tick0-1 の 2 tick だけを見る。"""
        events = [
            self._tick(0), self._tick(1), self._tick(2), self._tick(3),
            self._pos(0, 1, "浜"), self._pos(0, 2, "浜"),
            self._pos(2, 2, "森"),
            self._death(2, 2),
        ]
        out = em._extract_spatial_dispersion(events)
        assert out["first_death_tick"] == 2
        assert out["before_first_death"]["tick_count"] == 2
        assert out["before_first_death"]["mean_distinct_spots"] == 1.0

    def test_ejected_counts_as_terminal_outcome(self, em) -> None:
        """追放された player の位置も残り続けるため、EJECTED も死亡と同じ扱いにする。"""
        events = [
            self._tick(0), self._tick(1),
            self._pos(0, 1, "浜"),
            self._death(1, 1, outcome="EJECTED"),
        ]
        out = em._extract_spatial_dispersion(events)
        assert out["first_death_tick"] == 1

    def test_run_without_death_reports_none_instead_of_zero(self, em) -> None:
        """誰も死ななかった run では first_death_tick を None にし、死亡前の
        切り分けも返さない (= tick 0 で死んだと読める 0 を返さない)。"""
        events = [self._tick(0), self._pos(0, 1, "浜")]
        out = em._extract_spatial_dispersion(events)
        assert out["first_death_tick"] is None
        assert out["before_first_death"] is None

    def test_revive_does_not_count_as_death(self, em) -> None:
        """DEAD 以外の outcome 遷移 (蘇生・生存確定) は死亡として拾わない。"""
        events = [
            self._tick(0),
            self._pos(0, 1, "浜"),
            self._death(0, 1, outcome="SURVIVED"),
        ]
        out = em._extract_spatial_dispersion(events)
        assert out["first_death_tick"] is None


class TestClusteringMetricsIncludedInComputeMetrics:
    def test_compute_metrics_exposes_the_three_clustering_metrics(
        self, em, tmp_path
    ) -> None:
        """compute_metrics の戻り値に action_budget / speak_chains /
        spatial_dispersion が揃う (= 分析側が個別に呼ばずに済む)。"""
        events = [
            {"kind": "tick_start", "tick": 0, "payload": {}},
            {
                "kind": "position_change", "tick": 0, "player_id": 1,
                "payload": {"to_spot_id": "浜", "spot_name": "浜", "player_name": "エイダ"},
            },
            _action(0, 1, "speak"),
            _action(0, 1, "travel_to"),
        ]
        m = em.compute_metrics(_write_trace(tmp_path, events))
        assert m["action_budget"]["world_changing_share"] == 50.0
        assert m["speak_chains"]["next_action_after_speak"] == {"travel_to": 1}
        assert m["spatial_dispersion"]["mean_distinct_spots"] == 1.0
