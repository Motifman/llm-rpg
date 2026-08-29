"""REMOVE_ITEMの全本番入口が、部分消費しない一括削除へ接続されることを保証する。"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from ai_rpg_world.application.world_graph.player_interaction_application_service import (
    PlayerInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_stage_service import (
    SpotGraphScenarioEventStageService,
)
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)


def _called_function_names(function: object) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _call_lines(function: object, name: str) -> tuple[int, ...]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )
        if called_name == name:
            lines.append(node.lineno)
    return tuple(sorted(lines))


@pytest.mark.parametrize(
    "entrypoint",
    [
        SpotInteractionApplicationService._execute_item_interaction_with_repositories,
        SpotInteractionApplicationService._execute_interaction_with_repositories,
        PlayerInteractionApplicationService._remove_from,
        SpotGraphScenarioEventStageService._apply_event,
    ],
)
def test_every_remove_item_entrypoint_uses_bulk_removal(entrypoint: object) -> None:
    """4つの本番入口は単品ループへ戻らず、全量確保型の一括削除を呼ぶ。"""
    calls = _called_function_names(entrypoint)

    assert "remove_items_of_specs_from_inventory" in calls
    assert "remove_one_item_of_spec_from_inventory" not in calls


@pytest.mark.parametrize(
    "entrypoint",
    [
        SpotInteractionApplicationService._execute_item_interaction_with_repositories,
        SpotInteractionApplicationService._execute_interaction_with_repositories,
        PlayerInteractionApplicationService._execute_with_repositories,
    ],
)
def test_interactions_preflight_removals_before_world_flag_mutation(
    entrypoint: object,
) -> None:
    """道具・物体・対人操作は、世界フラグを書き換える前に削除全量を検証する。"""
    preflight_lines = _call_lines(entrypoint, "_require_removable_items")
    mutation_lines = _call_lines(entrypoint, "replace_from_interaction")

    assert preflight_lines
    assert mutation_lines
    assert max(preflight_lines) < min(mutation_lines)


@pytest.mark.parametrize(
    "entrypoint",
    [
        SpotInteractionService.execute_interaction,
        SpotInteractionService.execute_declared_interaction,
    ],
)
def test_spot_interactions_preflight_removals_before_applying_effects(
    entrypoint: object,
) -> None:
    """物体・道具操作は状態変更やloot抽選を始める前に削除量を検証する。"""
    preflight_lines = _call_lines(entrypoint, "_require_effect_item_removals")
    effect_lines = _call_lines(entrypoint, "apply_effects")

    assert preflight_lines
    assert effect_lines
    assert max(preflight_lines) < min(effect_lines)


def test_player_interaction_plans_removals_before_applying_effects() -> None:
    """対人操作も行為者・対象者の削除量を効果適用より先に解決する。"""
    plan_lines = _call_lines(
        PlayerInteractionApplicationService._execute_with_repositories,
        "plan_item_removals",
    )
    effect_lines = _call_lines(
        PlayerInteractionApplicationService._execute_with_repositories,
        "apply_effects",
    )

    assert plan_lines
    assert effect_lines
    assert max(plan_lines) < min(effect_lines)
