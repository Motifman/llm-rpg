"""実験の run は、設定を書かなくてもプロンプトを prompt dataset に保存することを保証する (#1631)。"""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def test_stub_run_without_any_capture_setting_writes_the_prompt_dataset(tmp_path: Path) -> None:
    """保存の設定を何も書かない smoke_stub の run でも、prompt_dataset/calls.jsonl に LLM 呼び出しが 1 行以上残る。"""
    from scripts.run_scenario_experiment import main

    config = json.loads((_REPO / "data/experiment_profiles/smoke_stub.json").read_text(encoding="utf-8"))
    config["profile"] = "capture_stub"
    config["max_world_ticks"] = 2
    config_path = tmp_path / "experiment.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    rc = main(
        [
            "--experiment-config",
            str(config_path),
            "--out",
            str(tmp_path / "run"),
            "--no-html",
            "--no-progress-jsonl",
            "--no-stderr-progress",
        ]
    )

    assert rc == 0
    calls = tmp_path / "run" / "prompt_dataset" / "calls.jsonl"
    assert calls.exists()
    assert calls.read_text(encoding="utf-8").splitlines()
