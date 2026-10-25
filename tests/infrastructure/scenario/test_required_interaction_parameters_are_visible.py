"""全シナリオで前提条件と effect が要求する入力が action 候補に表示されることを保証する。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (
    format_action_display_with_hints,
    required_parameter_hints,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
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
    preconditions = tuple(
        SimpleNamespace(
            condition_type=InteractionConditionTypeEnum(cond["condition_type"]),
            puzzle_input_key=cond.get("puzzle_input_key"),
        )
        for cond in raw.get("preconditions", [])
    )
    return SimpleNamespace(effects=effects, preconditions=preconditions)


def _declared_required_keys(raw: Mapping[str, Any]) -> list[str]:
    """JSON の宣言から、実行時に parameters から読まれるキーを列挙する。"""
    keys = [
        str(cond.get("puzzle_input_key"))
        for cond in raw.get("preconditions", [])
        if cond.get("condition_type") == "PUZZLE_INPUT_MATCH"
    ]
    keys += [
        str((effect.get("parameters") or {}).get("text_param_key", "text"))
        for effect in raw.get("effects", [])
        if effect.get("effect_type") == "WRITE_PLAYER_TEXT"
    ]
    return keys


def test_all_required_parameters_are_rendered_in_action_candidates() -> None:
    """全シナリオの PUZZLE_INPUT_MATCH と WRITE_PLAYER_TEXT は、宣言したキーを「が要る」と候補表示する。"""
    found: dict[str, list[str]] = {"PUZZLE_INPUT_MATCH": [], "WRITE_PLAYER_TEXT": []}
    violations: list[str] = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for interaction in _iter_interactions(raw):
            expected_keys = _declared_required_keys(interaction)
            if not expected_keys:
                continue
            hints = required_parameter_hints(_as_interaction(interaction))
            rendered = format_action_display_with_hints(
                str(interaction["action_name"]),
                hints,
                display_label=str(interaction.get("display_label") or ""),
            )
            declared = json.dumps(interaction, ensure_ascii=False)
            for kind in found:
                if kind in declared:
                    found[kind].append(f"{path.name}:{interaction['action_name']}")
            for key in expected_keys:
                if f'"{key}" が要る' not in rendered:
                    violations.append(f"{path.name}:{interaction['action_name']}: {rendered}")

    assert all(found.values()), f"監査対象から消えた種類がある: {found}"
    assert not violations, "\n".join(violations)
