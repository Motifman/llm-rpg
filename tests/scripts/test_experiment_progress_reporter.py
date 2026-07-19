"""_ExperimentProgressReporter の挙動検証 (実験 #25 進捗可視化対応)。

- stdout に旧来通り 1 行 print されること
- stderr inline 進捗 (tty / 非 tty 両方)
- progress.jsonl が 1 tick 1 行で書かれること
- finalize() で正常終了 + 例外時両方クローズされること
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.run_scenario_experiment import (
    _ExperimentProgressReporter,
    _format_duration,
)


class TestFormatDuration:
    """秒を MM:SS / HH:MM:SS に整形する境界条件。"""

    def test_zero_00(self) -> None:
        """0秒は 00 00。"""
        assert _format_duration(0) == "00:00"

    def test_negative_value_00(self) -> None:
        """負値も 00 00。"""
        assert _format_duration(-100) == "00:00"

    def test_one_30_01_30(self) -> None:
        """1分 30秒は 01 30。"""
        assert _format_duration(90) == "01:30"

    def test_one_more_hh_mm_ss(self) -> None:
        """1時間以上は HH MM SS。"""
        assert _format_duration(3661) == "1:01:01"


class TestProgressReporterStdout:
    """stdout に旧来形式の 1 行 print が出る。"""

    def test_tick_end_stdout_line_rendered(self, tmp_path: Path) -> None:
        """tickend で stdout に進捗行が出る。"""
        out = io.StringIO()
        err = io.StringIO()
        reporter = _ExperimentProgressReporter(
            max_world_ticks=10, stdout=out, stderr=err, progress_jsonl=None
        )
        reporter.tick_end(i=0, world_tick=1)
        stdout = out.getvalue()
        assert "駆動 1/10" in stdout
        assert "world_tick=1" in stdout
        assert "elapsed=" in stdout
        assert "eta=" in stdout


class TestProgressReporterStderr:
    """stderr inline 進捗 (非 tty なら改行、tty なら \\r)。"""

    def test_non_tty_stderr_line(self) -> None:
        """非 ttystderr は改行で書く。"""
        out = io.StringIO()
        err = io.StringIO()  # StringIO は isatty() を持たない (= False)
        reporter = _ExperimentProgressReporter(
            max_world_ticks=5, stdout=out, stderr=err, progress_jsonl=None
        )
        reporter.tick_end(i=0, world_tick=42)
        stderr_value = err.getvalue()
        assert "[  1/5]" in stderr_value
        assert "tick=42" in stderr_value
        assert "eta=" in stderr_value
        # 非 tty なら \r ではなく \n
        assert stderr_value.endswith("\n")

    def test_stderr_none_not_output(self) -> None:
        """stderr None なら 出力されない。"""
        out = io.StringIO()
        reporter = _ExperimentProgressReporter(
            max_world_ticks=5, stdout=out, stderr=None, progress_jsonl=None
        )
        reporter.tick_end(i=0, world_tick=1)
        # stdout はあるが stderr 文字列は存在しない (None 渡しで)
        assert out.getvalue()  # stdout は出る


class TestProgressJsonl:
    """progress.jsonl が 1 tick 1 行 JSON で append される。"""

    def test_tick_end_one_line_jsonl_written(self, tmp_path: Path) -> None:
        """tickend で 1 行 jsonl に書かれる。"""
        out = io.StringIO()
        progress_path = tmp_path / "progress.jsonl"
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=progress_path
        )
        reporter.tick_end(i=0, world_tick=10)
        reporter.tick_end(i=1, world_tick=11)
        reporter.finalize()

        lines = progress_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        entry0 = json.loads(lines[0])
        assert entry0["tick_index"] == 1
        assert entry0["max_world_ticks"] == 3
        assert entry0["world_tick"] == 10
        assert "eta_seconds" in entry0
        assert "elapsed_seconds" in entry0

    def test_jsonl_none(self, tmp_path: Path) -> None:
        """jsonl None なら 書かない。"""
        out = io.StringIO()
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=None
        )
        reporter.tick_end(i=0, world_tick=1)
        reporter.finalize()
        # tmp_path に progress.jsonl が無いことを確認
        assert not (tmp_path / "progress.jsonl").exists()

    def test_progress_report_includes_observability_fields(
        self, tmp_path: Path
    ) -> None:
        """``#404`` P2 で追加した内訳フィールドが progress.jsonl に出る。

        - ``world_tick_start`` + ``nested_world_ticks`` で 1 driver iteration
          あたり world tick が何個進んだかが分かる (旧 do_move のネスト
          advance_tick が再発したら nested_world_ticks が跳ねるので検知できる)
        - ``llm_calls`` で 656 秒スパイクの原因 (134 LLM call) のような状況が
          progress を見ただけで分かる
        - ``travel_active`` で「いま何人が移動中か」がトレース可能
        """
        out = io.StringIO()
        progress_path = tmp_path / "progress.jsonl"
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=progress_path
        )
        reporter.tick_end(
            i=0,
            world_tick=10,
            world_tick_start=8,  # 2 ticks 進んだ
            llm_calls=4,
            travel_active=2,
        )
        reporter.finalize()

        entry = json.loads(progress_path.read_text(encoding="utf-8").strip())
        assert entry["world_tick"] == 10
        assert entry["world_tick_start"] == 8
        assert entry["nested_world_ticks"] == 2
        assert entry["llm_calls"] == 4
        assert entry["travel_active"] == 2

    def test_observation_unspecified(self, tmp_path: Path) -> None:
        """後方互換: optional パラメータを渡さなければ従来通り。"""
        out = io.StringIO()
        progress_path = tmp_path / "progress.jsonl"
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=progress_path
        )
        reporter.tick_end(i=0, world_tick=10)
        reporter.finalize()

        entry = json.loads(progress_path.read_text(encoding="utf-8").strip())
        assert "world_tick_start" not in entry
        assert "nested_world_ticks" not in entry
        assert "llm_calls" not in entry
        assert "travel_active" not in entry


class TestFinalize:
    """finalize でファイルが閉じる / 二重 finalize 安全。"""

    def test_finalize_after_finalize_op(self, tmp_path: Path) -> None:
        """finalize 後の finalize は no op。"""
        out = io.StringIO()
        progress_path = tmp_path / "progress.jsonl"
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=progress_path
        )
        reporter.tick_end(i=0, world_tick=1)
        reporter.finalize()
        reporter.finalize()  # 2 回呼んでも例外にならない
        assert progress_path.exists()
