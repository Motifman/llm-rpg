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


@pytest.mark.parametrize(
    "entrypoint",
    [
        SpotInteractionApplicationService.execute_item_interaction,
        SpotInteractionApplicationService.execute_interaction,
        PlayerInteractionApplicationService._remove_from,
        SpotGraphScenarioEventStageService._apply_event,
    ],
)
def test_every_remove_item_entrypoint_uses_bulk_removal(entrypoint: object) -> None:
    """4つの本番入口は単品ループへ戻らず、全量確保型の一括削除を呼ぶ。"""
    calls = _called_function_names(entrypoint)

    assert "remove_items_of_specs_from_inventory" in calls
    assert "remove_one_item_of_spec_from_inventory" not in calls
