"""LLM が死んだ run は途中で止まり、report.md がそれを最初に言う。

供物競争 140 tick run は t47 で OpenRouter のクレジットが尽きたのに 140 tick 走り
切り、`make experiment` は exit 0 で終わった。report.md はこう書いた。

    - outcome: **LOSE**
    - last tick: 140 / max world ticks: 140
    | player_id | actions | successes | failures |
    | 1         | 20      | 20        | 0        |

**呼び出しの半分が落ちたことは 1 文字も出ていない。** しかも `failures` 列は tool の
失敗なので、**呼び出しが届かなかったぶんは行動として数えられず、失敗率が高いほど
report がきれいになる。**

対処は 2 つで、片方だけでは足りない。**止める** (層 2) と、**必ず見せる** (層 3)。
層 2 だけだと閾値未満の run が黙る。層 3 だけだと次も 82 tick 空回りする。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.run_scenario_experiment import _build_report, _drive_scenario

from ai_rpg_world.application.trace import JsonlTraceRecorder, TraceEventKind


class _Runtime:
    """指定した tick から `llm_abort_reason` を返しはじめる runtime。"""

    def __init__(self, *, abort_at: int | None) -> None:
        self.tick = 0
        self._abort_at = abort_at

    def get_player_ids(self):
        return ()

    def set_trace_recorder(self, recorder) -> None:
        self.recorder = recorder

    def current_tick(self) -> int:
        return self.tick

    def advance_tick(self) -> None:
        self.tick += 1

    def check_game_end(self):
        from ai_rpg_world.domain.world_graph.value_object.game_end_result import (
            GameEndResult,
        )

        return GameEndResult(is_ended=False, result=None, reason="ゲーム続行中")

    def llm_abort_reason(self) -> str | None:
        if self._abort_at is None or self.tick < self._abort_at:
            return None
        return "LLM 呼び出しが 8 件連続で失敗した (LLM_API_CALL_FAILED: 8)"

    def round_assignment_trace(self) -> list:
        return []

    def pop_llm_call_count(self) -> int:
        return 0

    def count_traveling_players(self) -> int:
        return 0

    def write_episodes_on_leaving(self, *, skip_reason: str | None = None) -> None:
        return None

    def shutdown(self, *, timeout: float) -> None:
        return None


def _drive(tmp_path: Path, monkeypatch, runtime: _Runtime, max_ticks: int) -> Any:
    import ai_rpg_world.presentation.spot_graph_game.runtime_manager as manager_module

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
    with JsonlTraceRecorder(tmp_path / "trace.jsonl") as recorder:
        return _drive_scenario(
            run_id="abort-test",
            scenario_path=Path("data/scenarios/offering_race_v2.json"),
            recorder=recorder,
            max_world_ticks=max_ticks,
            progress=lambda _message: None,
            reporter=None,
        )


class TestADeadRunStopsEarly:
    """止まるべき run が、残りの tick を空回りしない。"""

    def test_it_stops_before_the_deadline(self, tmp_path: Path, monkeypatch) -> None:
        """停止理由が立った tick で終わり、max_world_ticks まで進まない。

        140 tick run では t51 から 64 件連続で落ちた。閾値 8 なら t58 で
        止まり、**82 tick ぶんの空回りが消える**。
        """
        summary = _drive(tmp_path, monkeypatch, _Runtime(abort_at=3), max_ticks=20)

        assert summary["last_tick"] == 3
        assert summary["last_tick"] < summary["max_world_ticks"]

    def test_the_outcome_says_it_was_aborted(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """outcome が `LLM_ABORTED` になる。

        既存の `LLM_FAILURE` は「1 件も成功しなかった」の意味で使っている。
        **混ぜると過去 run の読みが変わる**ので別の名前にする。
        """
        summary = _drive(tmp_path, monkeypatch, _Runtime(abort_at=3), max_ticks=20)

        assert summary["outcome"] == "LLM_ABORTED"

    def test_the_reason_carries_the_streak(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """end_reason に連続件数と error_code が入る。

        止めた判断の根拠を、止めた場所に書く。trace を探し直させない。
        """
        summary = _drive(tmp_path, monkeypatch, _Runtime(abort_at=3), max_ticks=20)

        assert "8 件連続" in summary["end_reason"]
        assert "LLM_API_CALL_FAILED" in summary["end_reason"]

    def test_a_healthy_run_reaches_the_deadline(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """停止理由が立たない run は最後まで走る (**負の対照**)。

        ここが効かないと、**止めるべきでない run を engine が殺す**。
        """
        summary = _drive(tmp_path, monkeypatch, _Runtime(abort_at=None), max_ticks=5)

        assert summary["last_tick"] == 5
        assert summary["outcome"] != "LLM_ABORTED"

    def test_a_runtime_without_the_hook_still_runs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """`llm_abort_reason` を持たない runtime でも落ちない (**負の対照**)。

        presentation 単体テスト等の軽量 runtime を巻き込まない。
        """

        class _Hookless(_Runtime):
            llm_abort_reason = None  # type: ignore[assignment]

        summary = _drive(
            tmp_path, monkeypatch, _Hookless(abort_at=None), max_ticks=3
        )

        assert summary["last_tick"] == 3

    def test_a_broken_monitor_does_not_kill_the_run(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """`llm_abort_reason` が例外を投げても run は続く (**負の対照**)。

        監視の故障で実験そのものを落とさない。ただし**停止は永久に効かなく
        なる**ので、握った例外は warning に出す (握って黙るのは不可)。
        """

        class _Broken(_Runtime):
            def llm_abort_reason(self):
                raise RuntimeError("monitor is broken")

        summary = _drive(tmp_path, monkeypatch, _Broken(abort_at=None), max_ticks=3)

        assert summary["last_tick"] == 3


class TestTheReportAlwaysShowsTheCallHealth:
    """呼び出しの健全さを、探しに行かなくても読める場所に置く。"""

    def _trace(self, tmp_path: Path, outcomes: list[tuple[bool, str]]) -> Path:
        path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(path) as recorder:
            for index, (success, error_code) in enumerate(outcomes):
                recorder.record(
                    TraceEventKind.LLM_CALL,
                    tick=index,
                    player_id=1,
                    success=success,
                    error_code=error_code,
                )
        return path

    def _report(self, tmp_path: Path, trace_path: Path, **kwargs: Any) -> str:
        summary = {
            "outcome": kwargs.get("outcome", "LOSE"),
            "end_reason": kwargs.get("end_reason"),
            "last_tick": kwargs.get("last_tick", 140),
            "max_world_ticks": kwargs.get("max_world_ticks", 140),
            "elapsed_sec": 1.0,
        }
        return _build_report(
            scenario_path=Path("data/scenarios/offering_race_v2.json"),
            trace_path=trace_path,
            summary=summary,
        )

    def test_the_success_rate_is_in_the_header(self, tmp_path: Path) -> None:
        """呼び出し数と成功率が、冒頭の箇条書きに出る。

        **節の奥ではなく冒頭。** 140 tick run の report は 34 行あり、
        奥に置くと「outcome: LOSE / 140 tick 完走」だけを読んで閉じる。
        """
        trace = self._trace(
            tmp_path, [(True, "")] * 76 + [(False, "LLM_API_CALL_FAILED")] * 74
        )

        report = self._report(tmp_path, trace)
        header = report.split("##")[0]

        assert "150" in header
        assert "76" in header
        assert "51%" in header

    def test_the_error_codes_appear_when_calls_failed(self, tmp_path: Path) -> None:
        """失敗があるとき、error_code の内訳が出る。"""
        trace = self._trace(
            tmp_path,
            [(True, "")] * 2
            + [(False, "LLM_API_CALL_FAILED")] * 3
            + [(False, "LLM_WALL_TIME_CAP")],
        )

        report = self._report(tmp_path, trace)

        assert "LLM_API_CALL_FAILED: 3" in report
        assert "LLM_WALL_TIME_CAP: 1" in report

    def test_a_clean_run_shows_no_breakdown(self, tmp_path: Path) -> None:
        """全部成功した run では内訳の節を出さない (**負の対照**)。

        毎回出すと、読み手が「内訳がある = 何かおかしい」で拾えなくなる。
        **節の見出しそのものを見る** — 出力に無い語 (`error_code`) を否定
        しても、内訳を常時出す改変が素通りする。
        """
        trace = self._trace(tmp_path, [(True, "")] * 10)

        report = self._report(tmp_path, trace)

        assert "100%" in report
        assert "失敗内訳" not in report

    def test_a_run_without_llm_calls_says_nothing(self, tmp_path: Path) -> None:
        """呼び出しが 0 件の run では、成功率の行を出さない (**負の対照**)。

        stub run で「成功率 0%」と出ると、壊れた run と見分けがつかない。
        """
        trace = self._trace(tmp_path, [])

        report = self._report(tmp_path, trace)

        assert "llm calls" not in report

    def test_an_aborted_run_names_the_outcome(self, tmp_path: Path) -> None:
        """停止した run は outcome と理由の両方が report に出る。"""
        trace = self._trace(tmp_path, [(False, "LLM_API_CALL_FAILED")] * 8)

        report = self._report(
            tmp_path,
            trace,
            outcome="LLM_ABORTED",
            end_reason="LLM 呼び出しが 8 件連続で失敗した (LLM_API_CALL_FAILED: 8)",
            last_tick=58,
        )

        assert "outcome: **LLM_ABORTED**" in report
        assert "8 件連続" in report


class TestTheAbortReasonSurvivesTheFinalVerdict:
    """自ら止めた run の理由が、最後の全滅判定に丸められない。"""

    def test_the_streak_reason_is_kept_when_nothing_succeeded(
        self, tmp_path: Path
    ) -> None:
        """abort した run で成功が 0 件でも、end_reason が書き換わらない。

        `_classify_llm_run_health` は「1 件も成功しなかった run」を
        `LLM_FAILURE` に縮退させる。**abort は break のあと必ずここを通る**
        ので、認証ミスのように最初から全滅する run では
        「8 件連続で失敗した」が「4 件がすべて失敗した」に丸められる。
        止めた判断の根拠が、止めたあとに消える形だった。
        """
        from scripts.run_scenario_experiment import _classify_llm_run_health

        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            for index in range(8):
                recorder.record(
                    TraceEventKind.LLM_CALL,
                    tick=index,
                    player_id=1,
                    success=False,
                    error_code="LLM_API_CALL_FAILED",
                )
        streak_reason = "LLM 呼び出しが 8 件連続で失敗した (LLM_API_CALL_FAILED: 8)"

        outcome, reason, total, succeeded = _classify_llm_run_health(
            SimpleNamespace(path=trace_path),
            outcome="LLM_ABORTED",
            end_reason=streak_reason,
        )

        assert outcome == "LLM_ABORTED"
        assert reason == streak_reason
        assert (total, succeeded) == (8, 0)

    def test_a_plain_wipeout_still_becomes_llm_failure(
        self, tmp_path: Path
    ) -> None:
        """abort していない全滅 run は従来どおり `LLM_FAILURE` (**正の対照**)。

        上の分岐を広げすぎると、既存の砦が黙る。
        """
        from scripts.run_scenario_experiment import _classify_llm_run_health

        trace_path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(trace_path) as recorder:
            recorder.record(
                TraceEventKind.LLM_CALL,
                tick=0,
                player_id=1,
                success=False,
                error_code="LLM_AUTH_FAILED",
            )

        outcome, reason, _total, _succeeded = _classify_llm_run_health(
            SimpleNamespace(path=trace_path), outcome="TIMEOUT", end_reason=None
        )

        assert outcome == "LLM_FAILURE"
        assert "LLM_AUTH_FAILED" in str(reason)


class TestTheExitCodeSaysTheRunIsUnusable:
    """止まった run は、呼び出し元にも失敗として返る。"""

    @pytest.mark.parametrize("outcome", ["LLM_FAILURE", "LLM_ABORTED"])
    def test_both_llm_failures_return_one(
        self, tmp_path: Path, monkeypatch, outcome: str
    ) -> None:
        """`LLM_FAILURE` と `LLM_ABORTED` はどちらも終了コード 1 を返す。

        **成果物は残す** (実験データを守る)。壊れているのは run であって、
        そこまでに集めた trace ではない。
        """
        import scripts.run_scenario_experiment as runner
        from scripts.run_scenario_experiment import main

        monkeypatch.setattr(
            runner,
            "_drive_scenario",
            lambda **kwargs: {
                "outcome": outcome,
                "end_reason": "テスト用",
                "llm_call_count": 8,
                "llm_success_count": 0,
                "last_tick": 8,
                "elapsed_sec": 0.1,
                "max_world_ticks": kwargs["max_world_ticks"],
                "snapshot_save_dir": None,
                "snapshot_load_dir": None,
            },
        )
        out_dir = tmp_path / f"run-{outcome}"

        rc = main(
            [
                "--profile", "smoke_stub",
                "--out", str(out_dir),
                "--no-html",
                "--no-progress-jsonl",
                "--no-stderr-progress",
            ]
        )

        assert rc == 1
        assert (out_dir / "trace.jsonl").exists()
        assert f"outcome: **{outcome}**" in (
            out_dir / "report.md"
        ).read_text(encoding="utf-8")
