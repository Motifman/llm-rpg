"""scripts/analyze_llm_latency.py の集計挙動検証 (実験 #25 後続)。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.analyze_llm_latency import (
    _percentile,
    _summarize,
    analyze,
    iter_llm_call_events,
    main,
    render_report,
)


def _write_trace(path: Path, events: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _llm_call(
    *,
    wall: int,
    tps: float = 20.0,
    prompt: int = 100,
    completion: int = 50,
    model: str = "test/m",
    player_id: int = 1,
    tick: int = 1,
    success: bool = True,
    error_code=None,
    cost_usd: float = 0.0,
) -> dict:
    return {
        "seq": 1,
        "timestamp": "2026-06-06T00:00:00+00:00",
        "kind": "llm_call",
        "tick": tick,
        "player_id": player_id,
        "payload": {
            "model": model,
            "wall_latency_ms": wall,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "tps": tps,
            "success": success,
            "error_code": error_code,
            "cost_usd": cost_usd,
        },
    }


class TestPercentile:
    def test_empty_list_none(self) -> None:
        """空 list は None。"""
        assert _percentile([], 50) is None

    def test_single_value(self) -> None:
        """単一値はそのまま。"""
        assert _percentile([100.0], 50) == 100.0
        assert _percentile([100.0], 99) == 100.0

    def test_value(self) -> None:
        """中央値。"""
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_p95_boundary(self) -> None:
        """p95 の境界。"""
        # 0-99 の 100 値で p95 = 94.05
        values = [float(i) for i in range(100)]
        result = _percentile(values, 95)
        assert result is not None
        assert 94.0 <= result <= 95.0


class TestSummarize:
    def test_returns_empty_when_count_zero(self) -> None:
        """空なら count 0。"""
        s = _summarize([])
        assert s["count"] == 0
        assert s["p50"] is None
        assert s["max"] is None

    def test_value_summary_rendered(self) -> None:
        """値ありで summary が出る。"""
        s = _summarize([1.0, 2.0, 3.0, 4.0, 5.0])
        assert s["count"] == 5
        assert s["p50"] == 3.0
        assert s["max"] == 5.0
        assert s["mean"] == 3.0


class TestIterLlmCallEvents:
    def test_llm_call_filter(self, tmp_path: Path) -> None:
        """LLM CALL だけ filter される。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [
            {"kind": "llm_call", "payload": {"wall_latency_ms": 100}},
            {"kind": "action", "payload": {}},
            {"kind": "llm_call", "payload": {"wall_latency_ms": 200}},
            {"kind": "observation", "payload": {}},
        ])
        events = list(iter_llm_call_events([path]))
        assert len(events) == 2

    def test_line_skip(self, tmp_path: Path) -> None:
        """壊れた行は skip。"""
        path = tmp_path / "trace.jsonl"
        path.write_text(
            'not-json\n'
            '{"kind": "llm_call", "payload": {}}\n'
            '\n'  # 空行
            '{"kind": "llm_call", "payload": {}}\n',
            encoding="utf-8",
        )
        events = list(iter_llm_call_events([path]))
        assert len(events) == 2

    def test_emits_warning_for_missing_skip(
        self, tmp_path: Path, capsys
    ) -> None:
        """存在しないパスは warning で skip。"""
        events = list(iter_llm_call_events([tmp_path / "missing.jsonl"]))
        assert events == []


class TestAnalyze:
    def test_all_breakdown(self, tmp_path: Path) -> None:
        """全体と breakdown を集計。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [
            _llm_call(wall=1000, model="m1", player_id=1, success=True),
            _llm_call(wall=2000, model="m1", player_id=2, success=True),
            _llm_call(wall=5000, model="m2", player_id=1, success=True),
            _llm_call(
                wall=3000, model="m1", player_id=1, success=False,
                error_code="LLM_RATE_LIMIT",
            ),
        ])
        stats = analyze([path])
        assert stats["total_calls"] == 4
        assert stats["success_count"] == 3
        assert stats["failure_count"] == 1
        assert stats["by_error_code"]["LLM_RATE_LIMIT"] == 1
        assert "m1" in stats["by_model"]
        assert stats["by_model"]["m1"]["count"] == 3
        assert stats["by_model"]["m2"]["count"] == 1
        assert 1 in stats["by_player"]
        assert 2 in stats["by_player"]
        assert stats["by_player"][1]["count"] == 3

    def test_llm_call_event_total_zero(self, tmp_path: Path) -> None:
        """LLMCALLevent が無いと total0。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [
            {"kind": "action", "payload": {}},
        ])
        stats = analyze([path])
        assert stats["total_calls"] == 0
        assert stats["by_model"] == {}

    def test_payload_missing_does_not_crash(self, tmp_path: Path) -> None:
        """payload 欠落でも 落ちない。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [
            {"kind": "llm_call"},  # payload なし
            {"kind": "llm_call", "payload": {"wall_latency_ms": "not-int"}},
            _llm_call(wall=100),
        ])
        stats = analyze([path])
        # 1 件だけ集計に含まれる
        assert stats["overall"]["wall_latency_ms"]["count"] == 1


class TestRenderReport:
    def test_included(self, tmp_path: Path) -> None:
        """主要セクションが含まれる。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [
            _llm_call(wall=1000, success=True),
            _llm_call(wall=2000, success=True),
        ])
        stats = analyze([path])
        report = render_report(stats)
        assert "# LLM Call Latency Analysis" in report
        assert "## 全体サマリ" in report
        assert "## Model 別 wall_latency_ms" in report
        assert "## τ_sim 設計の手がかり" in report

    def test_sim_value_displayed(self, tmp_path: Path) -> None:
        """τ sim 推奨値が 表示される。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [
            _llm_call(wall=1000),
            _llm_call(wall=2000),
            _llm_call(wall=10000),  # p99 を引っ張る
        ])
        stats = analyze([path])
        report = render_report(stats)
        assert "推奨 τ_sim" in report

    def test_failure_zero_failure_breakdown_section_not_rendered(self, tmp_path: Path) -> None:
        """失敗 0 件なら 失敗内訳 section 出ない。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [_llm_call(wall=1000, success=True)])
        stats = analyze([path])
        report = render_report(stats)
        assert "失敗内訳" not in report


class TestMainCli:
    def test_file_exit_two(self, tmp_path: Path) -> None:
        """存在しないファイルは exit 2。"""
        ret = main([str(tmp_path / "missing.jsonl")])
        assert ret == 2

    def test_zero_llm_calls_exits_one(self, tmp_path: Path) -> None:
        """LLM CALL 0 件なら exit 1。"""
        path = tmp_path / "trace.jsonl"
        _write_trace(path, [{"kind": "action"}])
        ret = main([str(path)])
        assert ret == 1

    def test_markdown(self, tmp_path: Path) -> None:
        """markdown 出力。"""
        trace = tmp_path / "trace.jsonl"
        report = tmp_path / "report.md"
        _write_trace(trace, [_llm_call(wall=1000)])
        ret = main([str(trace), "--markdown", str(report)])
        assert ret == 0
        assert report.exists()
        assert "LLM Call Latency Analysis" in report.read_text(encoding="utf-8")

    def test_json(self, tmp_path: Path) -> None:
        """json 出力。"""
        trace = tmp_path / "trace.jsonl"
        json_out = tmp_path / "stats.json"
        _write_trace(trace, [_llm_call(wall=1000)])
        ret = main([str(trace), "--json", str(json_out)])
        assert ret == 0
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["total_calls"] == 1


class TestCostAggregation:
    """OpenRouter 経由の cost_usd を analyze が拾うか。"""

    def test_cost_usd_per_model_rendered(self, tmp_path: Path) -> None:
        """複数 event を合算し、model 別 cost も per-model_cost_usd_total に出る。"""
        trace = tmp_path / "trace.jsonl"
        _write_trace(
            trace,
            [
                _llm_call(wall=600, model="openrouter/google/gemma-4-31b-it", cost_usd=0.000005),
                _llm_call(wall=620, model="openrouter/google/gemma-4-31b-it", cost_usd=0.000007),
                _llm_call(wall=500, model="other/model", cost_usd=0.000002),
            ],
        )
        stats = analyze([trace])
        assert stats["overall"]["cost_usd_total"] == pytest.approx(0.000014)
        assert stats["by_model_cost_usd_total"]["openrouter/google/gemma-4-31b-it"] == pytest.approx(
            0.000012
        )
        assert stats["by_model_cost_usd_total"]["other/model"] == pytest.approx(0.000002)

    def test_cost_all_zero(self, tmp_path: Path) -> None:
        """OpenAI 直結 / vLLM 想定 (cost フィールドが 0 / 未設定)。"""
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, [_llm_call(wall=400), _llm_call(wall=500)])
        stats = analyze([trace])
        assert stats["overall"]["cost_usd_total"] == 0.0

    def test_cost_total_zero_render_cost_section_not_rendered(
        self, tmp_path: Path
    ) -> None:
        """cost が無い実験では report に cost section を出さない (ノイズ削減)。"""
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, [_llm_call(wall=400)])
        stats = analyze([trace])
        report = render_report(stats)
        assert "Cost (OpenRouter" not in report

    def test_cost_total_value_render_cost_section_rendered(
        self, tmp_path: Path
    ) -> None:
        """OpenRouter 実験では cost section が markdown に出る。"""
        trace = tmp_path / "trace.jsonl"
        _write_trace(
            trace,
            [_llm_call(wall=600, model="openrouter/m", cost_usd=0.000050)],
        )
        stats = analyze([trace])
        report = render_report(stats)
        assert "Cost (OpenRouter" in report
        assert "$0.000050" in report
