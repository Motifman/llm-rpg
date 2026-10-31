"""作業記憶へ置き換えるあいだ、プロンプトが一字一句変わらないことを保証する (#1630)。

比べる資料 ``tests/fixtures/prompts/*.json`` は、置き換えを始める前の main (``21a33e4c9``) で
``PYTHONPATH=. uv run python -m tests.support.prompt_baseline`` を走らせて書いた。
文面を変える PR は、同じコマンドで資料を書き直す。
"""

from __future__ import annotations

import json
import logging

import pytest
from tests.support.prompt_baseline import BASELINE_SCENARIOS, baseline_path, build_baseline


@pytest.mark.parametrize("scenario_name", BASELINE_SCENARIOS)
def test_prompts_match_the_baseline(scenario_name: str, caplog: pytest.LogCaptureFixture) -> None:
    """最初のターンの全員と、同じ待機を繰り返した直後のターンで、system とユーザー文が資料と一字一句同じになる。"""
    caplog.set_level(logging.CRITICAL)
    expected = json.loads(baseline_path(scenario_name).read_text(encoding="utf-8"))

    actual = build_baseline(scenario_name)

    assert actual == expected
