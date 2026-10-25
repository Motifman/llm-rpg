"""世界の tick で取りやめた 1 体ぶんの処理の件数が、run_end の要約と report.md の冒頭に必ず出ることを保証する。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.run_scenario_experiment import _build_report, _drive_scenario

from ai_rpg_world.application.trace import JsonlTraceRecorder


class _Runtime:
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

    def check_game_end(self):
        from ai_rpg_world.domain.world_graph.value_object.game_end_result import (
            GameEndResult,
        )

        return GameEndResult(is_ended=False, result=None, reason="ゲーム続行中")

    def round_assignment_trace(self) -> list:
        return []

    def pop_llm_call_count(self) -> int:
        return 0

    def count_traveling_players(self) -> int:
        return 0

    def write_episodes_on_leaving(self, *, skip_reason: str | None = None) -> None:
        return None

    def shutdown_async_events(self) -> None:
        return None

    def shutdown(self, *, timeout: float) -> None:
        return None


class _RuntimeWithFailures(_Runtime):
    def world_tick_failure_counts(self) -> dict[str, int]:
        return {"travel": 2, "monster_behavior": 1}


def _drive(tmp_path: Path, monkeypatch, runtime: _Runtime) -> dict[str, Any]:
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
            run_id="tick-failure-test",
            scenario_path=Path("data/scenarios/offering_race_v2.json"),
            recorder=recorder,
            max_world_ticks=2,
            progress=lambda _message: None,
            reporter=None,
        )


def _report(tmp_path: Path, counts: dict[str, int] | None) -> str:
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("", encoding="utf-8")
    summary = {
        "outcome": "TIMEOUT",
        "end_reason": None,
        "last_tick": 2,
        "max_world_ticks": 2,
        "elapsed_sec": 1.0,
        "world_tick_failure_counts": counts,
    }
    return _build_report(
        scenario_path=Path("data/scenarios/offering_race_v2.json"),
        trace_path=trace_path,
        summary=summary,
    )


class TestTheRunEndSummaryCarriesTheCounts:
    """run_end に渡す要約が、runtime の段ごとの件数と合計を持つこと。"""

    def test_counts_and_total_come_from_the_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """runtime が段ごとの件数を返すと、要約に同じ件数と合計が入る。"""
        summary = _drive(tmp_path, monkeypatch, _RuntimeWithFailures())

        assert summary["world_tick_failure_counts"] == {"travel": 2, "monster_behavior": 1}
        assert summary["world_tick_failure_total"] == 3

    def test_runtime_without_counts_is_marked_unmeasured(self, tmp_path: Path, monkeypatch) -> None:
        """件数を返せない runtime では 0 件と偽らず、件数と合計を None にする。"""
        summary = _drive(tmp_path, monkeypatch, _Runtime())

        assert summary["world_tick_failure_counts"] is None
        assert summary["world_tick_failure_total"] is None


class TestTheReportHeaderShowsTheCounts:
    """report.md の冒頭の要約に、取りやめた件数を必ず出すこと。"""

    def test_failures_are_in_the_header_with_breakdown_and_warning(self, tmp_path: Path) -> None:
        """件数が 0 でなければ、冒頭に合計と段ごとの内訳、効果の測定の前に切り分ける旨が出る。"""
        header = _report(tmp_path, {"travel": 2, "monster_behavior": 1}).split("##")[0]

        assert "世界の tick で例外を出した処理 (のべ): **3 件** (monster_behavior=1, travel=2)" in header
        assert "world_tick_unit_failed" in header

    def test_zero_failures_are_shown_without_warning(self, tmp_path: Path) -> None:
        """件数が 0 なら 0 と出し、切り分けの注意は出さない。"""
        header = _report(tmp_path, {}).split("##")[0]

        assert "- 世界の tick で例外を出した処理 (のべ): 0 件" in header
        assert "world_tick_unit_failed" not in header

    def test_unmeasured_is_not_shown_as_zero(self, tmp_path: Path) -> None:
        """件数が無い要約では 0 と書かず、未計測と出す。"""
        header = _report(tmp_path, None).split("##")[0]

        assert "- 世界の tick で例外を出した処理 (のべ): 未計測" in header
