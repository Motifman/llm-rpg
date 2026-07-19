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
    def test_LLM_call_数と_latency_と_token_を_集計する(self, em, tmp_path) -> None:
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

    def test_失敗率は_action_result_の_success_False_の_比率(self, em, tmp_path) -> None:
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
    def test_player_別_tool_histogram_と_失敗_error_code_集計(self, em, tmp_path) -> None:
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
    def test_tool_別_成功_失敗_error_code_breakdown(self, em, tmp_path) -> None:
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
    def test_PlayerDownedEvent_と_tend_to_player_を_数える(self, em, tmp_path) -> None:
        events = [
            {"kind": "observation", "payload": {"prose": "PlayerDownedEvent fired"}},
            {"kind": "action", "payload": {"tool": "tend_to_player"}},
            {"kind": "action_result", "payload": {"tool": "tend_to_player", "success": True}},
        ]
        chain = em.compute_metrics(_write_trace(tmp_path, events))["issue621_chain"]
        assert chain["PlayerDownedEvent"] >= 1
        assert chain["tend_to_player"] >= 1

    def test_実際のdownはstructured_player_downedから数える(self, em, tmp_path) -> None:
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
    def test_baseline_を_渡すと_比較行が_生成される(self, em, tmp_path) -> None:
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

    def test_no_summit_when_never_reached(self, em) -> None:
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

    def test_signal_fire_none_when_not_lit(self, em) -> None:
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

    def test_同一スポットに居る_tick_を_ペア別に数える(self, em) -> None:
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

    def test_未移動の_player_は_直前の_to_spot_id_を_carry_forward_する(self, em) -> None:
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

    def test_全員同スポットの_tick_数を_数える(self, em) -> None:
        events = [
            self._tick_start(0), self._tick_start(1),
            self._pos(0, 1, "浜", "エイダ"),
            self._pos(0, 2, "浜", "ノア"),
            self._pos(0, 3, "浜", "カイ"),
            self._pos(1, 3, "森", "カイ"),
        ]
        out = em._extract_coop_copresence(events)
        assert out["all_players_copresence_ticks"] == 1

    def test_position_change_が_一件も無い_player_は_数に入らない(self, em) -> None:
        """観測されていない player の位置は不明として扱い、過大集計しない。"""
        events = [
            self._tick_start(0),
            self._pos(0, 1, "浜", "エイダ"),
            {"kind": "llm_call", "tick": 0, "player_id": 4, "payload": {}},
        ]
        out = em._extract_coop_copresence(events)
        assert out["player_ids"] == [1]
        assert out["pair_copresence_ticks"] == {}

    def test_player_name_を_保持する(self, em) -> None:
        events = [self._tick_start(0), self._pos(0, 1, "浜", "エイダ")]
        out = em._extract_coop_copresence(events)
        assert out["player_names"]["P1"] == "エイダ"

    def test_イベントが空なら_全て_0_で返す(self, em) -> None:
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

    def test_hearsay_以外の_source_kind_は_数えない(self, em) -> None:
        events = [
            self._hearsay("リオ"),
            {"kind": "belief_evidence", "payload": {"source_kind": "prediction_error"}},
        ]
        out = em._extract_hearsay_evidence_by_speaker(events)
        assert out["total"] == 1
        assert out["by_speaker"] == {"リオ": 1}

    def test_話者別に_件数を_積む(self, em) -> None:
        events = [self._hearsay("リオ"), self._hearsay("リオ"), self._hearsay("ノア")]
        out = em._extract_hearsay_evidence_by_speaker(events)
        assert out["total"] == 3
        assert out["by_speaker"] == {"リオ": 2, "ノア": 1}


class TestPendingPredictionVerdicts:
    """PR-A: 約束 (pending_prediction_*) の kind 別件数と resolved の verdict 内訳。

    将来 pending_prediction_verdict_rejected のような未知 kind が増える想定
    のため、既知 3 種以外の suffix も拾えることを確認する。
    """

    def test_created_resolved_expired_の_件数を_数える(self, em) -> None:
        events = [
            {"kind": "pending_prediction_created", "payload": {}},
            {"kind": "pending_prediction_created", "payload": {}},
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "fulfilled"}},
            {"kind": "pending_prediction_expired", "payload": {}},
        ]
        out = em._extract_pending_prediction_verdicts(events)
        assert out["by_kind"] == {"created": 2, "resolved": 1, "expired": 1}

    def test_resolved_を_verdict_別に_内訳する(self, em) -> None:
        events = [
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "fulfilled"}},
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "fulfilled"}},
            {"kind": "pending_prediction_resolved", "payload": {"verdict": "broken"}},
        ]
        out = em._extract_pending_prediction_verdicts(events)
        assert out["resolved_verdict_breakdown"] == {"fulfilled": 2, "broken": 1}

    def test_未知の_pending_prediction_kind_も_by_kind_に_乗る(self, em) -> None:
        events = [{"kind": "pending_prediction_verdict_rejected", "payload": {}}]
        out = em._extract_pending_prediction_verdicts(events)
        assert out["by_kind"] == {"verdict_rejected": 1}


class TestGiveItem:
    """PR-A: give_item の action_result を成功/失敗別に数える。"""

    def test_give_item_の_成功_失敗を_数える(self, em) -> None:
        events = [
            {"kind": "action_result", "payload": {"tool": "give_item", "success": True}},
            {"kind": "action_result", "payload": {"tool": "give_item", "success": False}},
            {"kind": "action_result", "payload": {"tool": "travel_to", "success": True}},
        ]
        out = em._extract_give_item(events)
        assert out == {"total": 2, "success": 1, "fail": 1}

    def test_give_item_が_一件も無ければ_全て_0(self, em) -> None:
        out = em._extract_give_item([])
        assert out == {"total": 0, "success": 0, "fail": 0}


class TestCoopMetricsIncludedInComputeMetrics:
    def test_compute_metrics_に_新指標が_含まれる(self, em, tmp_path) -> None:
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
