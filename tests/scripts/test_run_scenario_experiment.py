"""scripts/run_scenario_experiment.py のレポートビルダーテスト (Phase 1d)。"""

import sys
from pathlib import Path

from ai_rpg_world.application.trace import (
    JsonlTraceRecorder,
    TraceEventKind,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import _build_report  # noqa: E402


class TestBuildReport:
    """trace.jsonl からの汎用レポート生成。"""

    def test_outcome_と各イベントカウントを含む(self, tmp_path: Path) -> None:
        """生成 Markdown に outcome / action 数 / memo 数 / プレイヤー別集計が出る。"""
        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as rec:
            rec.record(TraceEventKind.RUN_START, scenario="demo")
            rec.record(TraceEventKind.ACTION, tick=1, player_id=1, tool="press")
            rec.record(
                TraceEventKind.ACTION_RESULT,
                tick=1,
                player_id=1,
                tool="press",
                success=True,
            )
            rec.record(TraceEventKind.ACTION, tick=2, player_id=2, tool="examine")
            rec.record(
                TraceEventKind.ACTION_RESULT,
                tick=2,
                player_id=2,
                tool="examine",
                success=False,
            )
            rec.record(
                TraceEventKind.MEMO_ADD,
                tick=2,
                player_id=2,
                memo_id="m1",
                content="x",
            )
            rec.record(TraceEventKind.RUN_END, outcome="WIN", last_tick=2)

        report = _build_report(
            scenario_path=scenario,
            trace_path=trace_path,
            summary={
                "outcome": "WIN",
                "last_tick": 2,
                "max_ticks": 30,
                "elapsed_sec": 1.2,
            },
        )
        assert "outcome: **WIN**" in report
        assert "action: 2" in report
        assert "memo_add: 1" in report
        # プレイヤー別集計に 2 行
        assert "| 1 | 1 | 1 | 0 | 0 | 0 |" in report
        assert "| 2 | 1 | 0 | 1 | 1 | 0 |" in report

    def test_イベントが_observation_系のみでも_table_は_最小限で出る(
        self, tmp_path: Path
    ) -> None:
        """action がゼロでもクラッシュせず 0 件として表示される。"""
        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as rec:
            rec.record(TraceEventKind.RUN_START)
            rec.record(TraceEventKind.RUN_END, outcome="TIMEOUT", last_tick=0)
        report = _build_report(
            scenario_path=scenario,
            trace_path=trace_path,
            summary={
                "outcome": "TIMEOUT",
                "last_tick": 0,
                "max_ticks": 30,
                "elapsed_sec": 0.1,
            },
        )
        assert "action: 0" in report
        assert "memo_add: 0" in report
