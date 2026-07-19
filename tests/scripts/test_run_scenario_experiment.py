"""scripts/run_scenario_experiment.py のレポートビルダーテスト (Phase 1d)。"""

import json
import sys
from pathlib import Path

from ai_rpg_world.application.trace import (
    JsonlTraceRecorder,
    TraceEventKind,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import _build_report, main  # noqa: E402


class TestBuildReport:
    """trace.jsonl からの汎用レポート生成。"""

    def test_includes_outcome_event_count(self, tmp_path: Path) -> None:
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
                "max_world_ticks": 30,
                "elapsed_sec": 1.2,
            },
        )
        assert "outcome: **WIN**" in report
        assert "action: 2" in report
        assert "memo_add: 1" in report
        # position_change カウント (今回 0 件)
        assert "position_change: 0" in report
        # プレイヤー別集計に 2 行 (新列 moves あり)
        assert "| 1 | 1 | 1 | 0 | 0 | 0 | 0 |" in report
        assert "| 2 | 1 | 0 | 1 | 1 | 0 | 0 |" in report

    def test_position_change_event_moves_column_aggregated(
        self, tmp_path: Path
    ) -> None:
        """from_spot_id=None の初期配置は moves に含めず、移動だけがカウントされる。"""
        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as rec:
            rec.record(TraceEventKind.RUN_START)
            # 初期配置 (from_spot_id=None) → moves にカウントしない
            rec.record(
                TraceEventKind.POSITION_CHANGE,
                tick=0,
                player_id=1,
                from_spot_id=None,
                to_spot_id="a",
            )
            # 移動 (from_spot_id あり) → moves=1
            rec.record(
                TraceEventKind.POSITION_CHANGE,
                tick=5,
                player_id=1,
                from_spot_id="a",
                to_spot_id="b",
            )
            rec.record(
                TraceEventKind.POSITION_CHANGE,
                tick=10,
                player_id=1,
                from_spot_id="b",
                to_spot_id="c",
            )
            rec.record(TraceEventKind.RUN_END, outcome="WIN", last_tick=10)
        report = _build_report(
            scenario_path=scenario,
            trace_path=trace_path,
            summary={
                "outcome": "WIN",
                "last_tick": 10,
                "max_world_ticks": 30,
                "elapsed_sec": 1.0,
            },
        )
        assert "position_change: 3" in report
        # player 1: actions=0 successes=0 failures=0 memo_adds=0 memo_dones=0 moves=2
        assert "| 1 | 0 | 0 | 0 | 0 | 0 | 2 |" in report

    def test_event_observation_table_min_rendered(
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
                "max_world_ticks": 30,
                "elapsed_sec": 0.1,
            },
        )
        assert "action: 0" in report
        assert "memo_add: 0" in report


class TestMaxWorldTicksRename:
    """``#404`` P1 回帰: ``--max-world-ticks`` フラグと ``max_world_ticks`` フィールド。"""

    def test_uses_progress_jsonl_max_world_ticks_key(self, tmp_path: Path) -> None:
        """progress.jsonl entry の最大値フィールドが ``max_world_ticks``
        (旧 ``max_ticks``) になっている。集計スクリプトの追従漏れを検知する。"""
        from scripts.run_scenario_experiment import _ExperimentProgressReporter
        import io
        progress_path = tmp_path / "progress.jsonl"
        reporter = _ExperimentProgressReporter(
            max_world_ticks=10,
            stdout=io.StringIO(),
            stderr=None,
            progress_jsonl=progress_path,
        )
        reporter.tick_end(i=0, world_tick=1)
        reporter.finalize()
        entry = json.loads(progress_path.read_text(encoding="utf-8").strip())
        assert entry["max_world_ticks"] == 10
        assert "max_ticks" not in entry

    def test_build_report_max_world_ticks_displays(
        self, tmp_path: Path
    ) -> None:
        """report.md に ``max world ticks`` 行が含まれる (旧 ``max ticks`` リネーム)。"""
        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as rec:
            rec.record(TraceEventKind.RUN_START)
            rec.record(TraceEventKind.RUN_END, outcome="WIN", last_tick=5)
        report = _build_report(
            scenario_path=scenario,
            trace_path=trace_path,
            summary={
                "outcome": "WIN",
                "last_tick": 5,
                "max_world_ticks": 30,
                "elapsed_sec": 1.0,
            },
        )
        assert "max world ticks: 30" in report


class TestExperimentProfileManifest:
    """実験 profile/config が解決済み成果物として保存されることを保証する。"""

    def test_uses_manifest_run_start_resolved_config_remains_profile(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """profile の env が cfg に反映され、runtime へ同じ cfg が渡る。"""
        import scripts.run_scenario_experiment as runner

        captured: dict = {}

        def _fake_drive(**kwargs):
            captured.update(kwargs)
            return {
                "outcome": "TIMEOUT",
                "last_tick": 0,
                "elapsed_sec": 0.0,
                "max_world_ticks": kwargs["max_world_ticks"],
                "snapshot_save_dir": (
                    str(kwargs.get("snapshot_save_dir"))
                    if kwargs.get("snapshot_save_dir")
                    else None
                ),
                "snapshot_load_dir": None,
            }

        monkeypatch.setattr(runner, "_drive_scenario", _fake_drive)
        monkeypatch.setattr(runner, "_emit_html", lambda *a, **kw: None)
        out_dir = tmp_path / "out"
        rc = main(
            [
                "--profile",
                "smoke_stub",
                "--out",
                str(out_dir),
                "--no-html",
                "--no-progress-jsonl",
                "--no-stderr-progress",
            ]
        )

        assert rc == 0
        cfg = captured["runtime_config"]
        assert cfg.llm_client_kind == "stub"
        assert cfg.episodic_enabled is False
        # profile 使用時は runtime_config だけを見るので、外側 shell の値は混入しない。
        assert cfg.belief_evidence_enabled is False

        resolved = json.loads(
            (out_dir / "experiment.config.resolved.json").read_text(encoding="utf-8")
        )
        assert resolved["profile"] == "smoke_stub"
        assert resolved["runtime_config"]["llm_client_kind"] == "stub"
        assert resolved["runtime_config"]["belief_evidence_enabled"] is False
        assert "sk-secret" not in json.dumps(resolved, ensure_ascii=False)
        assert resolved["scenario_sha256"]
        assert resolved["git"]["dirty"] in (True, False)

        first = json.loads(
            (out_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        payload = first["payload"]
        assert payload["experiment_profile"] == "smoke_stub"
        assert payload["experiment_manifest_sha256"]
        assert payload["belief_evidence_enabled"] is False

    def test_experiment_config_scenario_max_world_ticks_can_use(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """--scenario 未指定でも config source からシナリオと tick 数を解決できる。"""
        import scripts.run_scenario_experiment as runner

        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "profile": "local_test",
                    "scenario": str(scenario),
                    "max_world_ticks": 7,
                    "runtime_config": {"LLM_CLIENT": "stub"},
                }
            ),
            encoding="utf-8",
        )
        captured: dict = {}

        def _fake_drive(**kwargs):
            captured.update(kwargs)
            return {
                "outcome": "TIMEOUT",
                "last_tick": 0,
                "elapsed_sec": 0.0,
                "max_world_ticks": kwargs["max_world_ticks"],
                "snapshot_save_dir": None,
                "snapshot_load_dir": None,
            }

        monkeypatch.setattr(runner, "_drive_scenario", _fake_drive)
        monkeypatch.setattr(runner, "_emit_html", lambda *a, **kw: None)

        rc = main(
            [
                "--experiment-config",
                str(config),
                "--out",
                str(tmp_path / "out"),
                "--no-html",
                "--no-progress-jsonl",
                "--no-stderr-progress",
            ]
        )

        assert rc == 0
        assert captured["scenario_path"] == scenario
        assert captured["max_world_ticks"] == 7

    def test_manifest_secret_mask_recursively_secret_values(self) -> None:
        """source に秘密値が混じっても manifest には生値を残さない。"""
        import scripts.run_scenario_experiment as runner

        masked = runner._mask_secret_values(
            {
                "runtime_config": {"OPENAI_API_KEY": "sk-secret"},
                "nested": [{"token": "tok-secret"}, {"plain": "visible"}],
            }
        )

        rendered = json.dumps(masked, ensure_ascii=False)
        assert "sk-secret" not in rendered
        assert "tok-secret" not in rendered
        assert masked["runtime_config"]["OPENAI_API_KEY"] == "***"
        assert masked["nested"][0]["token"] == "***"
        assert masked["nested"][1]["plain"] == "visible"
