"""全シナリオの初期所持品が、作者の説明文を prompt へ運ぶことを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def _initial_inventory_cases() -> list[tuple[Path, str, tuple[str, ...]]]:
    """初期所持品を持つ player と、その item の非空説明文を列挙する。"""
    cases: list[tuple[Path, str, tuple[str, ...]]] = []
    for path in sorted(_SCENARIO_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        descriptions = {
            item["id"]: str(item.get("description") or "").strip()
            for item in raw.get("item_specs", ())
        }
        for player in raw.get("players", ()):
            spec_ids = tuple(
                item if isinstance(item, str) else item["spec"]
                for item in player.get("initial_items", ())
            )
            expected = tuple(
                descriptions[spec_id]
                for spec_id in spec_ids
                if descriptions.get(spec_id)
            )
            if expected:
                cases.append((path, player["id"], expected))
    return cases


@pytest.mark.parametrize(
    ("scenario_path", "player_string_id", "descriptions"),
    _initial_inventory_cases(),
    ids=lambda value: value.name if isinstance(value, Path) else str(value),
)
def test_each_initial_item_description_reaches_its_owners_prompt(
    scenario_path: Path,
    player_string_id: str,
    descriptions: tuple[str, ...],
) -> None:
    """説明文のある初期所持品は、全シナリオで所持者の user prompt に現れる。"""
    runtime = create_world_runtime(scenario_path)
    player_id = PlayerId.create(
        runtime.id_mapper.get_int("player", player_string_id)
    )

    user_prompt = runtime.build_full_prompt(player_id)["messages"][1]["content"]

    for description in descriptions:
        assert description in user_prompt
