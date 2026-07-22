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

from scripts.run_scenario_experiment import (  # noqa: E402
    _build_report,
    _emit_html_artifacts,
    _render_map_viewer_html,
    main,
)


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
        assert "legacy HTML viewer" in report
        assert "map trace viewer" in report
        assert "episodic memory viewer" in report
        assert "timeline viewer" in report
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


class TestEmitHtmlArtifacts:
    """run 完了時に生成する HTML 成果物の挙動を保証する。"""

    def test_emits_legacy_and_three_viewers(
        self,
        tmp_path: Path,
        monkeypatch,
        capsys,
    ) -> None:
        """trace.html / viewer.html / episodic.html / timeline.html を同じ段で生成する。"""
        import scripts.run_scenario_experiment as runner

        trace_path = tmp_path / "trace.jsonl"
        trace_path.write_text("", encoding="utf-8")

        monkeypatch.setattr(
            runner,
            "_render_trace_html",
            lambda trace_path, *, title: "<html>legacy</html>",
        )
        monkeypatch.setattr(
            runner,
            "_render_map_viewer_html",
            lambda run_dir, trace_path, *, title: "<html>map</html>",
        )
        monkeypatch.setattr(
            runner,
            "_render_episodic_viewer_html",
            lambda trace_path, *, title: "<html>episodic</html>",
        )
        monkeypatch.setattr(
            runner,
            "_render_timeline_viewer_html",
            lambda trace_path, *, title: "<html>timeline</html>",
        )

        results = _emit_html_artifacts(
            run_dir=tmp_path,
            trace_path=trace_path,
            trace_html_path=tmp_path / "trace.html",
            title="demo run",
        )

        assert [r.name for r in results] == [
            "trace.html",
            "viewer.html",
            "episodic.html",
            "timeline.html",
        ]
        assert all(r.generated for r in results)
        assert (
            (tmp_path / "trace.html").read_text(encoding="utf-8")
            == "<html>legacy</html>"
        )
        assert (tmp_path / "viewer.html").read_text(encoding="utf-8") == "<html>map</html>"
        assert (
            (tmp_path / "episodic.html").read_text(encoding="utf-8")
            == "<html>episodic</html>"
        )
        assert (
            (tmp_path / "timeline.html").read_text(encoding="utf-8")
            == "<html>timeline</html>"
        )
        out = capsys.readouterr().out
        assert "[html] trace.html:" in out
        assert "[html] viewer.html:" in out
        assert "[html] episodic.html:" in out
        assert "[html] timeline.html:" in out

    def test_viewer_failure_is_reported_without_stopping_other_outputs(
        self,
        tmp_path: Path,
        monkeypatch,
        capsys,
    ) -> None:
        """個別 Viewer 生成が失敗しても警告を出し、残りの HTML は生成する。"""
        import scripts.run_scenario_experiment as runner

        trace_path = tmp_path / "trace.jsonl"
        trace_path.write_text("", encoding="utf-8")

        monkeypatch.setattr(
            runner,
            "_render_trace_html",
            lambda trace_path, *, title: "<html>legacy</html>",
        )

        def _raise_map(*args, **kwargs):
            raise RuntimeError("cytoscape unavailable")

        monkeypatch.setattr(runner, "_render_map_viewer_html", _raise_map)
        monkeypatch.setattr(
            runner,
            "_render_episodic_viewer_html",
            lambda trace_path, *, title: "<html>episodic</html>",
        )
        monkeypatch.setattr(
            runner,
            "_render_timeline_viewer_html",
            lambda trace_path, *, title: "<html>timeline</html>",
        )

        results = _emit_html_artifacts(
            run_dir=tmp_path,
            trace_path=trace_path,
            trace_html_path=tmp_path / "trace.html",
            title="demo run",
        )

        by_name = {r.name: r for r in results}
        assert by_name["viewer.html"].generated is False
        assert by_name["viewer.html"].error == "cytoscape unavailable"
        assert by_name["trace.html"].generated is True
        assert by_name["episodic.html"].generated is True
        assert by_name["timeline.html"].generated is True
        assert not (tmp_path / "viewer.html").exists()
        assert (tmp_path / "episodic.html").exists()
        assert (tmp_path / "timeline.html").exists()
        out = capsys.readouterr().out
        assert "[html-error] viewer.html: cytoscape unavailable" in out

    def test_map_viewer_vendor_fetch_error_includes_recovery_step(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Cytoscape 取得失敗時は vendor キャッシュ復旧手順をエラー文に含める。"""
        import scripts.build_trace_viewer as build_trace_viewer
        from scripts._viewer_vendor import VendorFetchError

        trace_path = tmp_path / "trace.jsonl"
        trace_path.write_text("", encoding="utf-8")
        (tmp_path / "scenario.json").write_text("{}", encoding="utf-8")

        def _raise_vendor_error(*args, **kwargs):
            raise VendorFetchError("offline mode: vendor not cached")

        monkeypatch.setattr(build_trace_viewer, "fetch_cytoscape", _raise_vendor_error)

        try:
            _render_map_viewer_html(tmp_path, trace_path, title="demo")
        except RuntimeError as e:
            message = str(e)
        else:
            raise AssertionError("vendor fetch failure must raise RuntimeError")

        assert "offline mode: vendor not cached" in message
        assert "scripts/build_trace_viewer.py <run_dir>" in message
        assert "Cytoscape vendor をキャッシュ" in message

    def test_no_html_skips_all_html_artifacts(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """--no-html を指定すると legacy HTML と 3 Viewer を一括で生成しない。"""
        import scripts.run_scenario_experiment as runner

        def _fake_drive(**kwargs):
            return {
                "outcome": "TIMEOUT",
                "last_tick": 0,
                "elapsed_sec": 0.0,
                "max_world_ticks": kwargs["max_world_ticks"],
                "snapshot_save_dir": None,
                "snapshot_load_dir": None,
            }

        def _fail_if_called(**kwargs):
            raise AssertionError("--no-html must skip HTML artifact generation")

        monkeypatch.setattr(runner, "_drive_scenario", _fake_drive)
        monkeypatch.setattr(runner, "_emit_html_artifacts", _fail_if_called)

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
        assert not (out_dir / "trace.html").exists()
        assert not (out_dir / "viewer.html").exists()
        assert not (out_dir / "episodic.html").exists()
        assert not (out_dir / "timeline.html").exists()


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

    def test_prompt_dataset_runtime_config_keeps_llm_api_key_none(self) -> None:
        """prompt dataset の run metadata には API key placeholder も保存しない。"""
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )
        import scripts.run_scenario_experiment as runner

        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key="sk-secret")

        payload = runner._prompt_dataset_runtime_config_payload(cfg)

        rendered = json.dumps(payload, ensure_ascii=False)
        assert payload["llm_api_key"] is None
        assert "sk-secret" not in rendered
        assert "***" not in rendered
