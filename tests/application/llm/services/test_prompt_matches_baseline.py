"""プロンプトを作業記憶から組むようにしても、文が一字一句変わらないことを保証する (#1630)。

比べる資料 ``tests/fixtures/prompts/`` は、組み立てを作業記憶へ切り替える前の main で
``PYTHONPATH=. uv run python -m tests.support.prompt_baseline`` を走らせて書いた
(どの commit で書いたかは ``tests/support/prompt_baseline.py`` の docstring)。
文面を変える PR は、同じコマンドで資料を書き直す。
"""

from __future__ import annotations

import json
import logging

import pytest
from tests.support.prompt_baseline import (
    BASELINE_SCENARIOS,
    EVERY_SCENARIO_PATH,
    baseline_path,
    build_baseline,
    build_every_scenario,
)


@pytest.fixture(autouse=True)
def _quiet(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.CRITICAL)


@pytest.mark.parametrize("scenario_name", BASELINE_SCENARIOS)
def test_prompts_match_the_baseline(scenario_name: str) -> None:
    """最初のターンの全員、同じ待機を繰り返した直後、記憶と知らせに中身があるターンで、system とユーザー文が資料と一字一句同じになる。"""
    expected = json.loads(baseline_path(scenario_name).read_text(encoding="utf-8"))

    actual = build_baseline(scenario_name)

    assert actual == expected


def test_every_scenario_matches_the_baseline() -> None:
    """data/scenarios の全シナリオの最初のターンの全員で、締めの一文の 2 通りと評価の段の文が、資料と同じ sha256 になる。"""
    expected = json.loads(EVERY_SCENARIO_PATH.read_text(encoding="utf-8"))

    assert build_every_scenario() == expected
