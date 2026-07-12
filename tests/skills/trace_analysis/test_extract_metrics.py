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
