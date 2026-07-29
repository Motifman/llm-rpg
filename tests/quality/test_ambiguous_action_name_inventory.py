"""全シナリオに残る多義的な裸の action_name を手動品質確認用に棚卸しする。

一覧を読むときは `uv run pytest tests/quality/test_ambiguous_action_name_inventory.py
-m quality -rs` で実行する。`-rs` が無いと pytest の既定表示では件数だけになり、
改名対象の中身が見えない。

この棚卸しは通常監査が落ちたとき、改名対象を人間が読める一覧として確認するための
補助である。改名後は通常監査側でも同じ denylist を hard に検査する。
"""

from __future__ import annotations

import pytest

from tests.infrastructure.scenario.test_interaction_action_name_audit import (
    _format_violations,
    _scenario_entries,
    find_ambiguous_bare_action_names,
)


@pytest.mark.quality
def test_list_ambiguous_bare_action_names_in_all_scenarios() -> None:
    """多義語 denylist に一致する action_name を、`-m quality -rs` 実行で一覧化する。"""
    violations = find_ambiguous_bare_action_names(_scenario_entries())
    if violations:
        pytest.skip(
            "ambiguous bare action names remain; list with "
            "`uv run pytest tests/quality/test_ambiguous_action_name_inventory.py "
            "-m quality -rs`:\n"
            + _format_violations(violations)
        )
