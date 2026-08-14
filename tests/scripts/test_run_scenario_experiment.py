"""scripts/run_scenario_experiment.py のレポートビルダーテスト (Phase 1d)。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from ai_rpg_world.application.trace import (
    JsonlTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import (  # noqa: E402
    _build_report,
    _classify_llm_run_health,
    _drive_scenario,
    _emit_html_artifacts,
    _outcome_and_reason,
    _runtime_config_mapping_from_source,
    _render_map_viewer_html,
    main,
)


class TestOutcomeAndReason:
    """世界側の終了判定を trace と集計へ渡す値へ変換する。"""

    def test_enum_result_and_reason_are_converted_together(self) -> None:
        """enum の repr でなく宣言値を返し、終了理由も同じ境界で整える。"""
        end_check = GameEndResult(
            is_ended=True,
            result=GameResultEnum.LOSE,
            reason="インポスター陣営が人数差を作った",
        )

        assert _outcome_and_reason(end_check) == (
            "LOSE",
            "インポスター陣営が人数差を作った",
        )

    def test_missing_result_uses_the_existing_ended_fallback(self) -> None:
        """結果と理由が無い既存経路は、ENDED と理由なしへ倒す。"""
        end_check = GameEndResult(is_ended=True, result=None, reason="")

        assert _outcome_and_reason(end_check) == ("ENDED", None)

    def test_drive_scenario_returns_the_declared_outcome_value(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """実験駆動の公開結果にも enum の repr でなく LOSE と理由を載せる。"""
        import ai_rpg_world.presentation.spot_graph_game.runtime_manager as manager_module

        class FakeRuntime:
            def __init__(self) -> None:
                self.tick = 0

            def get_player_ids(self):
                return ()

            def set_trace_recorder(self, recorder) -> None:
                self.recorder = recorder

            def current_tick(self) -> int:
                return self.tick

            def advance_tick(self) -> None:
                self.tick += 1

            def check_game_end(self) -> GameEndResult:
                return GameEndResult(
                    is_ended=True,
                    result=GameResultEnum.LOSE,
                    reason="インポスター陣営が人数差を作った",
                )

            def pop_llm_call_count(self) -> int:
                return 0

            def count_traveling_players(self) -> int:
                return 0

            def shutdown(self, *, timeout: float) -> None:
                assert timeout == 30.0

        runtime = FakeRuntime()
        state = SimpleNamespace(
            runtime=runtime,
            llm_wiring=SimpleNamespace(
                prompt_dataset_sink=None,
                llm_turn_trigger=SimpleNamespace(schedule_turn=lambda _pid: None),
            ),
        )

        class FakeManager:
            def __init__(self, **_kwargs) -> None:
                self._sessions = {"session": state}

            def create_character(self, _request):
                return SimpleNamespace(id="character")

            def create_session(self, _request):
                return SimpleNamespace(session_id="session")

        monkeypatch.setattr(manager_module, "GameRuntimeManager", FakeManager)
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            summary = _drive_scenario(
                run_id="run034-calibration",
                scenario_path=tmp_path / "scenario.json",
                max_world_ticks=5,
                recorder=recorder,
                progress=lambda _message: None,
            )

        assert summary["outcome"] == "LOSE"
        assert summary["end_reason"] == "インポスター陣営が人数差を作った"
        assert state.llm_wiring.llm_session_run_id == "run034-calibration"


class TestLlmRunHealth:
    """LLM 呼び出しが全滅した run を正常な TIMEOUT に見せない。"""

    def test_all_failed_calls_turn_timeout_into_llm_failure(
        self, tmp_path: Path
    ) -> None:
        """呼び出しが1件以上あり成功0件なら、LLM_FAILUREと失敗理由を返す。"""
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            recorder.record(
                TraceEventKind.LLM_CALL,
                success=False,
                error_code="LLM_AUTHENTICATION_ERROR",
            )
            outcome, reason, total, succeeded = _classify_llm_run_health(
                recorder,
                outcome="TIMEOUT",
                end_reason=None,
            )

        assert outcome == "LLM_FAILURE"
        assert "LLM_AUTHENTICATION_ERROR: 1" in reason
        assert (total, succeeded) == (1, 0)

    def test_one_success_keeps_the_world_outcome(self, tmp_path: Path) -> None:
        """失敗が混じっても1件成功していれば、世界側の終了結果を維持する。"""
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            recorder.record(TraceEventKind.LLM_CALL, success=False, error_code="NO_TOOL_CALL")
            recorder.record(TraceEventKind.LLM_CALL, success=True, error_code=None)
            outcome, reason, total, succeeded = _classify_llm_run_health(
                recorder,
                outcome="TIMEOUT",
                end_reason=None,
            )

        assert (outcome, reason) == ("TIMEOUT", None)
        assert (total, succeeded) == (2, 1)

    def test_no_calls_do_not_break_a_non_llm_world(self, tmp_path: Path) -> None:
        """LLM呼び出し0件は全滅とみなさず、LLMを使わない世界を壊さない。"""
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            outcome, reason, total, succeeded = _classify_llm_run_health(
                recorder,
                outcome="TIMEOUT",
                end_reason=None,
            )

        assert (outcome, reason) == ("TIMEOUT", None)
        assert (total, succeeded) == (0, 0)

    def test_main_preserves_artifacts_but_returns_failure(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """LLM_FAILUREでもtrace/reportを残し、呼び出し元には終了コード1を返す。"""
        import scripts.run_scenario_experiment as runner

        monkeypatch.setattr(
            runner,
            "_drive_scenario",
            lambda **kwargs: {
                "outcome": "LLM_FAILURE",
                "end_reason": "LLM 呼び出し 4 件がすべて失敗した",
                "llm_call_count": 4,
                "llm_success_count": 0,
                "last_tick": 4,
                "elapsed_sec": 0.1,
                "max_world_ticks": kwargs["max_world_ticks"],
                "snapshot_save_dir": None,
                "snapshot_load_dir": None,
            },
        )
        out_dir = tmp_path / "failed-run"

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

        assert rc == 1
        assert (out_dir / "trace.jsonl").exists()
        assert "outcome: **LLM_FAILURE**" in (
            out_dir / "report.md"
        ).read_text(encoding="utf-8")


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

    def test_includes_distinct_end_reason(self, tmp_path: Path) -> None:
        """世界内終了と外的停止を区別できるよう、終了理由をreportへ残す。"""
        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            recorder.record(
                TraceEventKind.RUN_END,
                outcome="ENDED",
                end_reason="外的停止 END_ON_ALL_DOWN: 行動可能プレイヤーがいない",
            )

        report = _build_report(
            scenario_path=scenario,
            trace_path=trace_path,
            summary={
                "outcome": "ENDED",
                "end_reason": (
                    "外的停止 END_ON_ALL_DOWN: 行動可能プレイヤーがいない"
                ),
                "last_tick": 3,
                "max_world_ticks": 30,
                "elapsed_sec": 0.1,
            },
        )

        assert (
            "end reason: 外的停止 END_ON_ALL_DOWN: 行動可能プレイヤーがいない"
            in report
        )

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

    def test_emits_legacy_and_four_viewers(
        self,
        tmp_path: Path,
        monkeypatch,
        capsys,
    ) -> None:
        """trace.html / viewer.html / episodic.html / timeline.html / prompt.html を
        同じ段で生成する。"""
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
        monkeypatch.setattr(
            runner,
            "_render_prompt_viewer_html",
            lambda run_dir: "<html>prompt</html>",
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
            "prompt.html",
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
        assert (
            (tmp_path / "prompt.html").read_text(encoding="utf-8")
            == "<html>prompt</html>"
        )
        out = capsys.readouterr().out
        assert "[html] trace.html:" in out
        assert "[html] viewer.html:" in out
        assert "[html] episodic.html:" in out
        assert "[html] timeline.html:" in out
        assert "[html] prompt.html:" in out

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

    _HISTORICAL_DEEPSEEK_PROFILES = (
        "belief_goal_full",
        "ablation_base",
        "belief_goal_memo_ab_keep_memo",
        "belief_goal_memo_ab_hide_memo",
        "station_drill",
        "station_drill_lean",
    )

    @staticmethod
    def _load_profile(profile_name: str) -> dict:
        return json.loads(
            (
                _REPO_ROOT
                / "data"
                / "experiment_profiles"
                / f"{profile_name}.json"
            ).read_text(encoding="utf-8")
        )

    def test_belief_profiles_keep_active_search_tools_off_for_memo_ab(self) -> None:
        """belief_goal_full と ablation_base は能動検索 2 tool を意図して OFF に揃える。"""
        for profile_name in ("belief_goal_full", "ablation_base"):
            profile = self._load_profile(profile_name)
            runtime_config = profile["runtime_config"]

            assert runtime_config["SEMANTIC_SEARCH_ENABLED"] is False
            assert runtime_config["EPISODIC_EXPLORE_RELATED_ENABLED"] is False
            assert runtime_config["EPISODIC_RECALL_ENABLED"] is True

    def test_station_drill_lean_captures_prompts_without_episodic_memory(self) -> None:
        """lean profile は記憶を有効化せず prompt dataset を警告方針で保存する。"""
        profile = self._load_profile("station_drill_lean")
        runtime_config = profile["runtime_config"]

        assert runtime_config["LLM_EPISODIC_ENABLED"] is False
        assert runtime_config["PROMPT_DATASET_CAPTURE_ENABLED"] is True
        assert runtime_config["PROMPT_DATASET_CAPTURE_FAILURE_POLICY"] == "warn"

    def test_station_drill_lean_keeps_the_long_run_comparison_conditions(
        self,
    ) -> None:
        """50 tick の長走比較は要約だけを足し、他の記憶機能を無効のまま保つ。"""
        profile = self._load_profile("station_drill_lean")

        # profile 全体ではなく、実験の測定結果を直接変える条件だけを固定する。
        # 補助機能の追加など、比較条件に影響しない更新まで妨げないためである。
        assert profile["scenario"] == "data/scenarios/station_drill.json"
        assert "run 034" in profile["description"]
        assert "並列数を 8" in profile["description"]
        assert profile["max_world_ticks"] == 50
        assert profile["runtime_config"]["LLM_MEETING_SERIAL_TURNS"] is False
        assert profile["runtime_config"]["SHORT_TERM_MEMORY_KIND"] == "rolling_summary"
        assert {
            key: profile["runtime_config"][key]
            for key in (
                "LLM_EPISODIC_ENABLED",
                "LLM_EPISODIC_SUBJECTIVE_ENABLED",
                "EPISODIC_RECALL_ENABLED",
                "SEMANTIC_LLM_GIST_ENABLED",
                "SEMANTIC_SEARCH_ENABLED",
                "BELIEF_EVIDENCE_ENABLED",
                "BELIEF_CONSOLIDATION_ENABLED",
                "GOAL_STORE_ENABLED",
                "GOAL_REVISION_ENABLED",
            )
        } == {
            "LLM_EPISODIC_ENABLED": False,
            "LLM_EPISODIC_SUBJECTIVE_ENABLED": False,
            "EPISODIC_RECALL_ENABLED": False,
            "SEMANTIC_LLM_GIST_ENABLED": False,
            "SEMANTIC_SEARCH_ENABLED": False,
            "BELIEF_EVIDENCE_ENABLED": False,
            "BELIEF_CONSOLIDATION_ENABLED": False,
            "GOAL_STORE_ENABLED": False,
            "GOAL_REVISION_ENABLED": False,
        }
        assert {
            key: profile["runtime_config"][key]
            for key in (
                "LLM_MODEL",
                "OPENROUTER_PROVIDER",
                "LLM_REASONING_EFFORT",
                "LLM_TURN_PARALLEL_WORKERS",
            )
        } == {
            "LLM_MODEL": "openrouter/deepseek/deepseek-v4-flash",
            "OPENROUTER_PROVIDER": "DeepSeek",
            "LLM_REASONING_EFFORT": "none",
            "LLM_TURN_PARALLEL_WORKERS": 8,
        }

    def test_station_drill_thinking_differs_only_in_measured_runtime_settings(self) -> None:
        """thinking 比較腕は lean から provider と熟考だけを変える。"""
        lean = self._load_profile("station_drill_lean")
        thinking = self._load_profile("station_drill_thinking")
        expected = dict(lean)
        expected["profile"] = "station_drill_thinking"
        expected["description"] = (
            "thinking の効果とコストを測る比較用。run 034 では 1 tick の呼び出しが"
            "最大 8 人ぶん発生し、4 並列では 2 波に分かれたため既定を 8 とする。"
            "station_drill_lean との差は provider と reasoning effort の 2 つだけ。"
        )
        expected["runtime_config"] = dict(lean["runtime_config"])
        expected["runtime_config"]["OPENROUTER_PROVIDER"] = "Cloudflare"
        expected["runtime_config"]["LLM_REASONING_EFFORT"] = "minimal"

        assert thinking == expected
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            _runtime_config_mapping_from_source(thinking)
        )
        assert cfg.openrouter_provider == "Cloudflare"
        assert cfg.llm_reasoning_effort == "minimal"
        assert cfg.llm_turn_parallel_workers == 8

    def test_station_drill_deepseek_auto_only_changes_provider_and_tool_choice(
        self,
    ) -> None:
        """DeepSeek auto 比較腕は thinking から provider と tool_choice だけを変える。"""
        thinking = self._load_profile("station_drill_thinking")
        deepseek_auto = self._load_profile("station_drill_deepseek_auto")
        expected = dict(thinking)
        expected["profile"] = "station_drill_deepseek_auto"
        expected["description"] = (
            "thinking を維持したまま DeepSeek のキャッシュ安定性を測る比較用。"
            "station_drill_thinking との差は provider と tool_choice の 2 つだけ。"
        )
        expected["runtime_config"] = dict(thinking["runtime_config"])
        expected["runtime_config"]["OPENROUTER_PROVIDER"] = "DeepSeek"
        expected["runtime_config"]["LLM_TOOL_CHOICE"] = "auto"

        assert deepseek_auto == expected
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            _runtime_config_mapping_from_source(deepseek_auto)
        )
        assert cfg.openrouter_provider == "DeepSeek"
        assert cfg.llm_reasoning_effort == "minimal"
        assert cfg.llm_tool_choice == "auto"
        assert cfg.reason_first_two_step_enabled is False

    def test_deepseek_auto_without_session_id_changes_only_that_setting(
        self,
    ) -> None:
        """session_id 無しの比較腕は基準 profile から送信設定だけを変える。"""
        base = self._load_profile("station_drill_deepseek_auto")
        without_session = self._load_profile(
            "station_drill_deepseek_auto_without_session"
        )
        expected = dict(base)
        expected["profile"] = "station_drill_deepseek_auto_without_session"
        expected["description"] = (
            "DeepSeek auto の session_id だけを外し、配信先固定によるタイムアウト集中と"
            "キャッシュ率への影響を測る比較用。"
        )
        expected["runtime_config"] = dict(base["runtime_config"])
        expected["runtime_config"]["LLM_SESSION_ID_ENABLED"] = False

        assert without_session == expected
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            _runtime_config_mapping_from_source(without_session)
        )
        assert cfg.llm_session_id_enabled is False

    def test_belief_goal_v4_inherits_keep_memo_with_new_model_routing(self) -> None:
        """v4 標準 profile は既存 A 腕を変えず、識別情報とモデル経路だけを更新する。"""
        base = self._load_profile("belief_goal_memo_ab_keep_memo")
        new_profile = self._load_profile("belief_goal_v4")
        expected = dict(base)
        expected["profile"] = "belief_goal_v4"
        expected["description"] = (
            "v4 の標準的な観察 run。memo tool と記憶・信念・目的・停滞系を有効化する。"
        )
        expected["runtime_config"] = dict(base["runtime_config"])
        expected["runtime_config"]["LLM_MODEL"] = (
            "openrouter/deepseek/deepseek-v4-flash-0731"
        )
        expected["runtime_config"]["OPENROUTER_PROVIDER"] = "Cloudflare"

        assert base["runtime_config"]["LLM_MODEL"] == (
            "openrouter/deepseek/deepseek-v4-flash"
        )
        assert base["runtime_config"]["OPENROUTER_PROVIDER"] == "DeepSeek"
        assert new_profile == expected

        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            _runtime_config_mapping_from_source(new_profile)
        )
        assert cfg.llm_model == "openrouter/deepseek/deepseek-v4-flash-0731"
        assert cfg.openrouter_provider == "Cloudflare"

    def test_historical_deepseek_profiles_keep_original_model_routing(self) -> None:
        """過去 run の意図を記録する既存6 profile は旧版と DeepSeek の組み合わせを保つ。"""
        for profile_name in self._HISTORICAL_DEEPSEEK_PROFILES:
            runtime_config = self._load_profile(profile_name)["runtime_config"]

            assert runtime_config["LLM_MODEL"] == (
                "openrouter/deepseek/deepseek-v4-flash"
            ), profile_name
            assert runtime_config["OPENROUTER_PROVIDER"] == "DeepSeek", profile_name

    def test_memo_ab_profiles_differ_only_by_memo_tool_exposure(self) -> None:
        """memo A/B の2腕は MEMO_TOOLS_ENABLED 以外の runtime_config を揃える。"""
        keep = self._load_profile("belief_goal_memo_ab_keep_memo")
        hide = self._load_profile("belief_goal_memo_ab_hide_memo")
        keep_config = keep["runtime_config"]
        hide_config = hide["runtime_config"]

        differing_keys = {
            key
            for key in set(keep_config) | set(hide_config)
            if keep_config.get(key) != hide_config.get(key)
        }

        assert differing_keys == {"MEMO_TOOLS_ENABLED"}
        assert keep_config["MEMO_TOOLS_ENABLED"] is True
        assert hide_config["MEMO_TOOLS_ENABLED"] is False

    def test_memo_ab_profiles_use_v4_scenario_for_run003_comparison(self) -> None:
        """memo A/B の2腕は run 003 と同じ v4 scenario を明示し、上書き忘れを防ぐ。"""
        for profile_name in (
            "belief_goal_memo_ab_keep_memo",
            "belief_goal_memo_ab_hide_memo",
        ):
            profile = self._load_profile(profile_name)

            assert profile["scenario"] == "data/scenarios/survival_island_v4_coop.json"

    def test_memo_ab_profiles_render_mountain_view_from_hidden_cove(self) -> None:
        """memo A/B の profile から組んだ runtime は、拠点の隠し入江で山影を見せる。"""
        for profile_name in (
            "belief_goal_memo_ab_keep_memo",
            "belief_goal_memo_ab_hide_memo",
        ):
            profile = self._load_profile(profile_name)
            cfg = ResolvedLlmRuntimeConfig.from_mapping(
                _runtime_config_mapping_from_source(profile)
            )
            runtime = create_world_runtime(
                _REPO_ROOT / profile["scenario"],
                config=cfg,
            )
            player_id = PlayerId(1)
            _teleport_player(runtime, int(player_id.value), "hidden_cove")

            text = runtime.build_llm_context(player_id).current_state_text

            assert "切り立った山影が見える" in text

    def test_memo_ab_profiles_keep_active_search_tools_off(self) -> None:
        """memo A/B では能動検索 2 tool を false に保ち、既存の episodic recall だけを残す。"""
        for profile_name in (
            "belief_goal_memo_ab_keep_memo",
            "belief_goal_memo_ab_hide_memo",
        ):
            profile = self._load_profile(profile_name)
            runtime_config = profile["runtime_config"]

            assert runtime_config["SEMANTIC_SEARCH_ENABLED"] is False
            assert runtime_config["EPISODIC_EXPLORE_RELATED_ENABLED"] is False
            assert runtime_config["EPISODIC_RECALL_ENABLED"] is True
            assert runtime_config["MEMO_DISTILL_ENABLED"] is True

    def test_smoke_stub_does_not_set_active_search_tool_flags(self) -> None:
        """smoke_stub は能動検索 2 tool を明示せず、既定 false のままにする。"""
        profile = self._load_profile("smoke_stub")
        runtime_config = profile["runtime_config"]

        assert "SEMANTIC_SEARCH_ENABLED" not in runtime_config
        assert "EPISODIC_EXPLORE_RELATED_ENABLED" not in runtime_config

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
        assert cfg.reason_first_two_step_enabled is False
        # profile 使用時は runtime_config だけを見るので、外側 shell の値は混入しない。
        assert cfg.belief_evidence_enabled is False

        resolved = json.loads(
            (out_dir / "experiment.config.resolved.json").read_text(encoding="utf-8")
        )
        assert resolved["profile"] == "smoke_stub"
        assert resolved["runtime_config"]["llm_client_kind"] == "stub"
        assert resolved["runtime_config"]["reason_first_two_step_enabled"] is False
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


def _teleport_player(runtime, player_id: int, spot_id: str) -> None:  # noqa: ANN001
    """prompt 確認用に player の位置だけを spot graph 上で移す。"""
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(player_id)
    spot = SpotId.create(runtime.id_mapper.get_int("spot", spot_id))
    try:
        graph.unplace_entity(entity_id)
    except Exception:
        pass
    graph.place_entity(entity_id, spot)
    runtime._spot_graph_repo.save(graph)
