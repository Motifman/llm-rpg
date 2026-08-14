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


def test_secret_leak_job_runs_for_main_push_and_every_pull_request() -> None:
    """漏洩検査 job は main への push と全 pull request の両方で起動する。"""
    workflow = _workflow()

    assert workflow["on"]["push"]["branches"] == ["main"]
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
