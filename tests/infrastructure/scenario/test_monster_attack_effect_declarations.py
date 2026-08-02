"""島シナリオの既存モンスター能力が、固定対応表なしで宣言されることを保証する。"""

import json
from pathlib import Path


_SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_EXPECTED = {
    "island_wolf": {
        "effect_type": "bleeding", "chance": 0.5,
        "duration_ticks": 12, "value": 1.0,
    },
    "feral_dog": {
        "effect_type": "bleeding", "chance": 0.5,
        "duration_ticks": 12, "value": 1.0,
    },
    "swamp_snake": {
        "effect_type": "poison", "chance": 0.6,
        "duration_ticks": 10, "value": 1.0,
    },
    "giant_crab": {
        "effect_type": "bleeding", "chance": 0.35,
        "duration_ticks": 8, "value": 1.0,
    },
}


def test_every_existing_island_monster_keeps_its_attack_effect_declaration() -> None:
    """全シナリオを走査し、対象4種の各出現箇所が現行能力値を宣言する。"""
    found: dict[str, list[str]] = {template_id: [] for template_id in _EXPECTED}
    for path in sorted(_SCENARIO_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for template in (raw.get("monsters") or {}).get("templates", []):
            template_id = template.get("id")
            if template_id not in _EXPECTED:
                continue
            assert template.get("attack_status_effects") == [_EXPECTED[template_id]], (
                f"{path.name}: {template_id} の状態異常能力宣言が現行値と異なる"
            )
            found[template_id].append(path.name)

    assert all(found.values()), f"対象テンプレートを走査できていない: {found}"
