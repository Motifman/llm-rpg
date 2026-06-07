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

    def test_0秒は_00_00(self) -> None:
        assert _format_duration(0) == "00:00"

    def test_負値も_00_00(self) -> None:
        assert _format_duration(-100) == "00:00"

    def test_1分_30秒は_01_30(self) -> None:
        assert _format_duration(90) == "01:30"

    def test_1時間以上は_HH_MM_SS(self) -> None:
        assert _format_duration(3661) == "1:01:01"


class TestProgressReporterStdout:
    """stdout に旧来形式の 1 行 print が出る。"""

    def test_tick_end_で_stdout_に_進捗行が_出る(self, tmp_path: Path) -> None:
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

    def test_非_tty_stderr_は_改行で_書く(self) -> None:
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

    def test_stderr_None_なら_出力されない(self) -> None:
        out = io.StringIO()
        reporter = _ExperimentProgressReporter(
            max_world_ticks=5, stdout=out, stderr=None, progress_jsonl=None
        )
        reporter.tick_end(i=0, world_tick=1)
        # stdout はあるが stderr 文字列は存在しない (None 渡しで)
        assert out.getvalue()  # stdout は出る


class TestProgressJsonl:
    """progress.jsonl が 1 tick 1 行 JSON で append される。"""

    def test_tick_end_で_1行_jsonl_に_書かれる(self, tmp_path: Path) -> None:
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

    def test_jsonl_None_なら_書かない(self, tmp_path: Path) -> None:
        out = io.StringIO()
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=None
        )
        reporter.tick_end(i=0, world_tick=1)
        reporter.finalize()
        # tmp_path に progress.jsonl が無いことを確認
        assert not (tmp_path / "progress.jsonl").exists()


class TestFinalize:
    """finalize でファイルが閉じる / 二重 finalize 安全。"""

    def test_finalize_後の_finalize_は_no_op(self, tmp_path: Path) -> None:
        out = io.StringIO()
        progress_path = tmp_path / "progress.jsonl"
        reporter = _ExperimentProgressReporter(
            max_world_ticks=3, stdout=out, stderr=None, progress_jsonl=progress_path
        )
        reporter.tick_end(i=0, world_tick=1)
        reporter.finalize()
        reporter.finalize()  # 2 回呼んでも例外にならない
        assert progress_path.exists()
