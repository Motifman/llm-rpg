"""全シナリオの object.state 生値表示を手動品質確認用に棚卸しする。

一覧を読むときは `uv run pytest tests/quality/test_scenario_state_display_inventory.py
-m quality -rs` で実行する。`-rs` が無いと pytest の既定表示では件数だけになり、
棚卸し対象の中身が見えない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.world_graph.entity.spot_object import VISIBLE_STATE_TAGS_KEY
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


@pytest.mark.quality
def test_list_raw_visible_state_values_in_all_scenarios() -> None:
    """v4 以外に残る raw key=value 表示を、`-m quality -rs` 実行で一覧化する。"""
    leaks: list[str] = []
    for path in sorted(_SCENARIOS.glob("*.json")):
        result = ScenarioLoader().load_from_file(path)
        for interior in result.interiors.values():
            for obj in interior.objects:
                visible = obj.visible_state()
                raw_keys = [key for key in visible if key != VISIBLE_STATE_TAGS_KEY]
                for key in raw_keys:
                    leaks.append(
                        f"{path.name}: object={obj.name!r} id={obj.object_id.value} "
                        f"key={key!r} visible={visible!r}"
                    )

    if leaks:
        pytest.skip(
            "raw visible state values remain; list with "
            "`uv run pytest tests/quality/test_scenario_state_display_inventory.py "
            "-m quality -rs`:\n"
            + "\n".join(leaks)
        )
