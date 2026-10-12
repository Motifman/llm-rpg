"""report.md が、行動の呼び出しと記憶の部品・Jev の呼び出しを分けて、回数・トークン・費用・待ち時間を部品ごとに出すことを保証する (#1617)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.run_scenario_experiment import _build_report

from ai_rpg_world.application.trace import JsonlTraceRecorder, TraceEventKind

_HEADER = "| 呼び出し | 回数 | 失敗 | 入力トークン | 出力トークン | 費用 (USD) | 待ち時間の合計 (秒) |"


def _action(*, success: bool, prompt: int, completion: int, cost: float, latency_ms: int) -> tuple[str, dict[str, Any]]:
    return (
        TraceEventKind.LLM_CALL,
        {
            "success": success,
            "error_code": None if success else "LLM_API_CALL_FAILED",
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cost_usd": cost,
            "wall_latency_ms": latency_ms,
        },
    )


def _aux(
    component: str,
    *,
    success: bool = True,
    prompt: int | None,
    completion: int | None,
    cost: float | None,
    latency_ms: int,
) -> tuple[str, dict[str, Any]]:
    return (
        TraceEventKind.AUX_LLM_CALL,
        {
            "component": component,
            "model": "m",
            "success": success,
            "error_code": None if success else "X",
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cached_tokens": None,
            "cost_usd": cost,
            "wall_latency_ms": latency_ms,
            "question_names": [],
        },
    )


def _report(tmp_path: Path, events: list[tuple[str, dict[str, Any]]]) -> list[str]:
    trace_path = tmp_path / "trace.jsonl"
    recorder = JsonlTraceRecorder(trace_path)
    for kind, payload in events:
        recorder.record(kind, tick=1, **payload)
    recorder.close()
    text = _build_report(
        scenario_path=Path("data/scenarios/offering_race_v2.json"),
        trace_path=trace_path,
        summary={
            "outcome": "TIMEOUT",
            "last_tick": 1,
            "max_world_ticks": 1,
            "elapsed_sec": 1.0,
            "world_tick_failure_counts": {},
        },
    )
    return text.splitlines()


class TestActionAndMemoryCallsAreSeparateRows:
    """行動と記憶の部品が別の行に分かれ、部品ごとに集計されることを保証する。"""

    def test_each_component_gets_its_own_row_with_totals(self, tmp_path: Path) -> None:
        """行動 2 回と要約 2 回・書き起こし 1 回を渡すと、表の行が行動・要約・書き起こしに分かれ、それぞれの回数・失敗・トークン・費用・待ち時間の合計が出る。"""
        lines = _report(
            tmp_path,
            [
                _action(success=True, prompt=100, completion=20, cost=0.002, latency_ms=1500),
                _action(success=False, prompt=200, completion=20, cost=0.001, latency_ms=2000),
                _aux("short_term_summary", prompt=50, completion=10, cost=0.0004, latency_ms=700),
                _aux("short_term_summary", success=False, prompt=60, completion=0, cost=0.0001, latency_ms=300),
                _aux("episode_writing", prompt=900, completion=300, cost=0.0015, latency_ms=4200),
            ],
        )

        start = lines.index(_HEADER)
        rows = lines[start + 2 : start + 5]
        assert rows == [
            "| 行動 | 2 | 1 | 300 | 40 | $0.0030 | 3.5 |",
            "| 短期記憶の要約 (short_term_summary) | 2 | 1 | 110 | 10 | $0.0005 | 1.0 |",
            "| エピソードの書き起こし (episode_writing) | 1 | 0 | 900 | 300 | $0.0015 | 4.2 |",
        ]

    def test_header_line_splits_total_cost_between_action_and_memory(self, tmp_path: Path) -> None:
        """冒頭の要約に、取れた費用の合計と、その行動ぶん・記憶の部品と Jev ぶんの内訳が 1 行で出る。"""
        lines = _report(
            tmp_path,
            [
                _action(success=True, prompt=1, completion=1, cost=0.003, latency_ms=1),
                _aux("short_term_summary", prompt=1, completion=1, cost=0.001, latency_ms=1),
            ],
        )

        assert "- 費用 (取れた分の合計): $0.0040 = 行動 $0.0030 + 記憶の部品と Jev $0.0010" in lines


class TestUnavailableCostIsNotShownAsZero:
    """費用やトークンが取れない呼び出しを $0 と見せないことを保証する。"""

    def test_jev_row_without_any_cost_says_unavailable(self, tmp_path: Path) -> None:
        """Jev の呼び出しがすべて費用・トークン無しなら、その行のトークンと費用は「取れない」と出る。"""
        lines = _report(
            tmp_path,
            [
                _aux("typed_judgment", prompt=None, completion=None, cost=None, latency_ms=800),
                _aux("typed_judgment", prompt=None, completion=None, cost=None, latency_ms=1200),
            ],
        )

        assert "| Jev の型付き判断 (typed_judgment) | 2 | 0 | 取れない | 取れない | 取れない | 2.0 |" in lines

    def test_partially_unavailable_cost_shows_the_sum_and_the_missing_count(self, tmp_path: Path) -> None:
        """一部の呼び出しだけ費用が無いとき、取れた分の合計と、取れなかった回数を並べて出す。"""
        lines = _report(
            tmp_path,
            [
                _aux("episode_subjective", prompt=10, completion=5, cost=0.0002, latency_ms=1000),
                _aux("episode_subjective", prompt=10, completion=5, cost=None, latency_ms=1000),
            ],
        )

        assert (
            "| 主観の書き込み (episode_subjective) | 2 | 0 | 20 | 10 | $0.0002 + 取れない 1 回 | 2.0 |"
            in lines
        )

    def test_header_line_counts_calls_without_cost(self, tmp_path: Path) -> None:
        """費用が取れない呼び出しがあると、冒頭の要約にその回数が添えられる。"""
        lines = _report(
            tmp_path,
            [
                _action(success=True, prompt=1, completion=1, cost=0.003, latency_ms=1),
                _aux("typed_judgment", prompt=None, completion=None, cost=None, latency_ms=1),
            ],
        )

        assert (
            "- 費用 (取れた分の合計): $0.0030 = 行動 $0.0030 + 記憶の部品と Jev $0.0000。"
            "費用が取れない呼び出し 1 回"
        ) in lines


class TestMissingRecordsAreVisible:
    """記録できなかった呼び出しと、呼び出しが無かったことが report から読めることを保証する。"""

    def test_record_failures_are_counted_per_component(self, tmp_path: Path) -> None:
        """aux_llm_call_record_failed があると、部品ごとの件数を「記録できなかった呼び出し」として出す。"""
        lines = _report(
            tmp_path,
            [
                (TraceEventKind.AUX_LLM_CALL_RECORD_FAILED, {"component": "episode_writing", "error_type": "OSError"}),
                (TraceEventKind.AUX_LLM_CALL_RECORD_FAILED, {"component": "episode_writing", "error_type": "OSError"}),
            ],
        )

        assert "- 記録できなかった呼び出し: episode_writing=2 (この回数は上の表に入っていない)" in lines

    def test_no_memory_calls_says_zero_instead_of_omitting(self, tmp_path: Path) -> None:
        """記憶の部品と Jev の呼び出しが 1 件も無いとき、表の下に 0 件だと明記する (省略して測っていないと誤読させない)。"""
        lines = _report(
            tmp_path,
            [_action(success=True, prompt=1, completion=1, cost=0.0, latency_ms=1)],
        )

        assert "- 記憶の部品と Jev の呼び出し: 0 件" in lines
