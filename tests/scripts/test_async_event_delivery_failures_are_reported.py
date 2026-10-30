"""非同期のハンドラの失敗の件数が、run_end の要約と report.md の冒頭に必ず出ることを保証する (design_decisions D1824-16)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.run_scenario_experiment import _build_report

from tests.scripts.test_world_tick_failures_are_reported import _drive, _Runtime


class _RuntimeWithAsyncFailures(_Runtime):
    def async_event_delivery_failure_counts(self) -> dict[str, int]:
        return {"handler_failed": 2, "shutdown_timeout": 1}


def _report(tmp_path: Path, counts: dict[str, int] | None) -> str:
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("", encoding="utf-8")
    summary: dict[str, Any] = {
        "outcome": "TIMEOUT",
        "end_reason": None,
        "last_tick": 2,
        "max_world_ticks": 2,
        "elapsed_sec": 1.0,
        "world_tick_failure_counts": {},
        "async_event_delivery_failure_counts": counts,
    }
    return _build_report(
        scenario_path=Path("data/scenarios/offering_race_v2.json"),
        trace_path=trace_path,
        summary=summary,
    )


class TestTheRunEndSummaryCarriesTheCounts:
    """run_end に渡す要約が、runtime の理由ごとの件数と合計を持つこと。"""

    def test_counts_and_total_come_from_the_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """runtime が理由ごとの件数を返すと、要約に同じ件数と合計が入る。"""
        summary = _drive(tmp_path, monkeypatch, _RuntimeWithAsyncFailures())

        assert summary["async_event_delivery_failure_counts"] == {"handler_failed": 2, "shutdown_timeout": 1}
        assert summary["async_event_delivery_failure_total"] == 3

    def test_runtime_without_counts_is_marked_unmeasured(self, tmp_path: Path, monkeypatch) -> None:
        """件数を返せない runtime では 0 件と偽らず、件数と合計を None にする。"""
        summary = _drive(tmp_path, monkeypatch, _Runtime())

        assert summary["async_event_delivery_failure_counts"] is None
        assert summary["async_event_delivery_failure_total"] is None


class TestTheReportHeaderShowsTheCounts:
    """report.md の冒頭の要約に、非同期のハンドラの失敗の件数を必ず出すこと。"""

    def test_failures_are_in_the_header_with_breakdown_and_warning(self, tmp_path: Path) -> None:
        """件数が 0 でなければ、冒頭に合計と理由ごとの内訳、trace で切り分ける旨が出る。"""
        header = _report(tmp_path, {"handler_failed": 2, "shutdown_timeout": 1}).split("##")[0]

        assert "非同期のハンドラの失敗 (のべ): **3 件** (handler_failed=2, shutdown_timeout=1)" in header
        assert "async_event_delivery_failed" in header

    def test_zero_failures_are_shown_without_warning(self, tmp_path: Path) -> None:
        """件数が 0 なら 0 と出し、切り分けの注意は出さない。"""
        header = _report(tmp_path, {}).split("##")[0]

        assert "- 非同期のハンドラの失敗 (のべ): 0 件" in header
        assert "async_event_delivery_failed" not in header

    def test_unmeasured_is_not_shown_as_zero(self, tmp_path: Path) -> None:
        """件数が無い要約では 0 と書かず、未計測と出す。"""
        header = _report(tmp_path, None).split("##")[0]

        assert "- 非同期のハンドラの失敗 (のべ): 未計測" in header
