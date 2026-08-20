"""CI の各 job が、役割ごとの検査と固定された依存を使うことを保証する。"""

from __future__ import annotations

from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    """YAML 1.1 の真偽値変換を避け、GitHub の on キーを文字列のまま読む。"""
    return yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _run_commands(job: dict) -> tuple[str, ...]:
    return tuple(
        str(step["run"])
        for step in job["steps"]
        if isinstance(step, dict) and "run" in step
    )


def test_secret_leak_job_runs_for_protected_pushes_and_every_pull_request() -> None:
    """漏洩検査はmain・大型統合先へのpushと全pull requestで起動する。"""
    workflow = _workflow()

    assert workflow["on"]["push"]["branches"] == [
        "main",
        "codex/uow-rearchitecture",
    ]
    assert "pull_request" in workflow["on"]
    assert "secret-leak" in workflow["jobs"]


def test_secret_leak_job_directly_runs_the_repository_scanner() -> None:
    """漏洩検査 job は pytest を介さず、リポジトリ走査スクリプトを直接実行する。"""
    commands = _run_commands(_workflow()["jobs"]["secret-leak"])

    assert commands == ("bash scripts/check_no_internal_hostnames.sh",)


def test_test_and_quality_jobs_use_python_lower_bound_and_frozen_uv_lock() -> None:
    """通常試験と品質検査は Python 3.10 と同じ uv.lock の解決結果を使う。"""
    jobs = _workflow()["jobs"]

    for job_name in ("test", "quality-goldens"):
        job = jobs[job_name]
        setup_python = next(
            step
            for step in job["steps"]
            if step.get("uses") == "actions/setup-python@v5"
        )
        assert setup_python["with"]["python-version"] == "3.10"
        setup_uv = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
        )
        assert setup_uv["with"]["version"] == "0.11.28"
        assert setup_uv["with"]["cache-dependency-glob"] == "uv.lock"
        commands = _run_commands(job)
        assert "uv sync --locked --extra export" in commands
        assert any(command.startswith("uv run --frozen pytest") for command in commands)


def test_the_test_job_spreads_pytest_across_the_runner_cores() -> None:
    """通常試験は ``-n auto`` で走らせ、runner の実コア数へ並列度を委ねる。

    数値を固定すると runner の種類が変わったときに余らせるか、逆に取り合って
    遅くなる。実測では並列 1 で 129 秒、2 で 47 秒、4 で 32 秒、8 で 26 秒と
    4 で頭打ちになり、どの並列度でも 1 件も落ちなかった。
    """
    commands = _run_commands(_workflow()["jobs"]["test"])

    assert "uv run --frozen pytest -n auto" in commands


def test_the_quality_job_regenerates_goldens_without_parallel_workers() -> None:
    """品質検査は並列にしない。golden の書き込み順で中身が変わるのを防ぐ。

    同じファイルへ書き出す golden があるため、worker が競合すると差分検査が
    不安定になる。11 件で 51 秒しかかからず、通常試験と並列に走るので短縮の
    必要もない。
    """
    commands = _run_commands(_workflow()["jobs"]["quality-goldens"])
    pytest_commands = [c for c in commands if c.startswith("uv run --frozen pytest")]

    assert pytest_commands, "品質検査が pytest を実行していない"
    assert all("-n" not in command.split() for command in pytest_commands)
