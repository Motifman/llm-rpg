"""tool 引数名の分類と、行動履歴へ保存する射影を保証する。"""

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.contracts import action_argument_classification
from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    ACTION_ARGUMENT_CLASSIFICATIONS,
    ActionArgumentClassificationError,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    project_action_arguments_for_history,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


_SCENARIO = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "scenarios"
    / "station_drill.json"
)


def test_projection_keeps_copyable_values_and_only_free_text_names() -> None:
    """完全一致値は正規形で残し、自由文は値を保存せず引数名だけ残す。"""

    identifiers, free_text_names = project_action_arguments_for_history(
        {
            "target_label": "当番表",
            "action_name": "write_note",
            "parameters": {"text": "長い本文をここへ書く"},
            "say_inline": "書いておこう",
            "stealth": False,
            "memo_ids": ["memo-a", "memo-b"],
            "inner_thought": "すぐ下の専用行に出る",
            "expected_result": "予測行に出る",
        }
    )

    assert identifiers == {
        "action_name": "write_note",
        "memo_ids": '["memo-a","memo-b"]',
        "stealth": "false",
        "target_label": "当番表",
    }
    assert free_text_names == ("parameters", "say_inline")
    assert "長い本文をここへ書く" not in repr((identifiers, free_text_names))


def test_startup_rejects_an_exposed_argument_missing_from_the_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """露出中の schema property を分類表から消すと runtime 構築時に落ちる。"""

    monkeypatch.setattr(
        action_argument_classification,
        "ACTION_ARGUMENT_CLASSIFICATIONS",
        {
            name: kind
            for name, kind in ACTION_ARGUMENT_CLASSIFICATIONS.items()
            if name != "action_name"
        },
    )

    with pytest.raises(ActionArgumentClassificationError, match="action_name"):
        create_world_runtime(_SCENARIO)
