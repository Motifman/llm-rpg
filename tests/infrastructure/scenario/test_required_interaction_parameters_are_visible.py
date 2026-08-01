"""全シナリオで effect が要求する入力が action 候補に表示されることを保証する。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (
    format_action_display_with_hints,
    required_parameter_hints,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _iter_interactions(value: Any) -> Iterable[Mapping[str, Any]]:
    """JSON 全体を再帰走査し、action_name を持つ interaction を取りこぼさない。"""
    if isinstance(value, Mapping):
        if "action_name" in value:
            yield value
        for child in value.values():
            yield from _iter_interactions(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_interactions(child)


def _as_interaction(raw: Mapping[str, Any]) -> SimpleNamespace:
    """監査対象 JSON を required_parameter_hints が読む最小形へ変換する。"""
    effects = tuple(
        SimpleNamespace(
            effect_type=InteractionEffectTypeEnum(effect["effect_type"]),
            parameters=effect.get("parameters") or {},
        )
        for effect in raw.get("effects", [])
    )
    return SimpleNamespace(effects=effects)


def test_all_required_effect_parameters_are_rendered_in_action_candidates() -> None:
    """全シナリオの WRITE_PLAYER_TEXT は宣言したキーを「が要る」と候補表示する。"""
    found: list[str] = []
    violations: list[str] = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for interaction in _iter_interactions(raw):
            effects = interaction.get("effects", [])
            if not any(
                effect.get("effect_type") == "WRITE_PLAYER_TEXT"
                for effect in effects
            ):
                continue
            hints = required_parameter_hints(_as_interaction(interaction))
            rendered = format_action_display_with_hints(
                str(interaction["action_name"]),
                hints,
                display_label=str(interaction.get("display_label") or ""),
            )
            expected_keys = [
                str((effect.get("parameters") or {}).get("text_param_key", "text"))
                for effect in effects
                if effect.get("effect_type") == "WRITE_PLAYER_TEXT"
            ]
            found.append(f"{path.name}:{interaction['action_name']}")
            for key in expected_keys:
                if f"{key} が要る" not in rendered:
                    violations.append(
                        f"{path.name}:{interaction['action_name']}: {rendered}"
                    )

    assert found, "WRITE_PLAYER_TEXT を使う action が監査対象から消えている"
    assert not violations, "\n".join(violations)
