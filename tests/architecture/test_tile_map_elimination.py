"""本番のプロンプト経路に、タイル用の参照と設定が戻らないことを保証する。"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import fields
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_spot_graph_wiring_module_is_removed() -> None:
    """退役したスポット用の配線モジュールは読み込めない。"""
    with pytest.raises(ImportError):
        importlib.import_module("ai_rpg_world.application.llm.wiring.spot_graph_wiring")


def test_spot_graph_wiring_is_not_exported() -> None:
    """退役したスポット用の配線関数はパッケージから再公開されない。"""
    wiring_pkg = importlib.import_module("ai_rpg_world.application.llm.wiring")
    assert not hasattr(wiring_pkg, "create_spot_graph_wiring")
    assert "create_spot_graph_wiring" not in getattr(wiring_pkg, "__all__", ())


def test_full_wiring_is_retired_from_package() -> None:
    """退役した create_llm_agent_wiring はパッケージから再公開されない。"""
    wiring_pkg = importlib.import_module("ai_rpg_world.application.llm.wiring")
    assert not hasattr(wiring_pkg, "create_llm_agent_wiring")
    assert "create_llm_agent_wiring" not in getattr(wiring_pkg, "__all__", ())


def test_create_observation_recipient_resolver_has_no_tile_repositories() -> None:
    """観測の配信先の組み立ては、物理マップと当たり判定の保存先を受け取らない。"""
    from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
        create_observation_recipient_resolver,
    )
    sig = inspect.signature(create_observation_recipient_resolver)
    assert "physical_map_repository" not in sig.parameters
    assert "hit_box_repository" not in sig.parameters


@pytest.mark.parametrize("relative_path", [
    "application/llm/services/prompt_builder.py",
    "application/llm/services/prompt_builder_config.py",
    "application/llm/services/spot_graph_current_state_formatter.py",
])
def test_prompt_path_does_not_import_tile_query_or_formatter(relative_path: str) -> None:
    """本番のプロンプト構築とスポット用整形は、タイル用の問い合わせ・整形を直接読み込まない。"""
    path = _REPO_ROOT / "src/ai_rpg_world" / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    retired = {
        "ai_rpg_world.application.world.services.world_query_service",
        "ai_rpg_world.application.llm.services.current_state_formatter",
    }
    imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    imports.update(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not imports & retired


def test_prompt_limits_have_no_tile_settings() -> None:
    """PromptLimits はタイルの表示切替も視界距離も設定項目として持たない。"""
    from ai_rpg_world.application.llm.services.prompt_builder_config import PromptLimits
    assert {field.name for field in fields(PromptLimits)} == {"default_action_instruction"}


def test_current_state_query_has_no_tile_settings() -> None:
    """現在状態の問い合わせにはプレイヤーと移動先取得の指定だけがあり、タイル用の設定は無い。"""
    from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
    assert {field.name for field in fields(GetPlayerCurrentStateQuery)} == {
        "player_id", "include_available_moves",
    }


def test_spot_graph_augmenting_world_query_module_is_removed() -> None:
    """退役したスポットの状態を追加する問い合わせモジュールは読み込めない。"""
    with pytest.raises(ImportError):
        importlib.import_module(
            "ai_rpg_world.application.world_graph.spot_graph_augmenting_world_query"
        )


def test_world_runtime_does_not_import_in_memory_physical_map_repository() -> None:
    """本番の実行環境は InMemoryPhysicalMapRepository を読み込まない。"""
    runtime_file = _REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py"
    text = runtime_file.read_text(encoding="utf-8")
    assert "InMemoryPhysicalMapRepository" not in text


@pytest.mark.parametrize("relative_path", [
    "ui_context_builder.py",
    "executors/movement_executor.py",
    "executors/world_executor.py",
    "tool_catalog/world.py",
    "tool_catalog/movement.py",
    "tool_catalog/pursuit.py",
    "tool_catalog/combat.py",
    "_argument_resolvers/movement_resolver.py",
    "_argument_resolvers/world_resolver.py",
    "_argument_resolvers/combat_skill_resolver.py",
])
def test_tile_llm_modules_are_removed(relative_path: str) -> None:
    """旧タイル用LLMの実装ファイルは存在せず、再公開によって復活しない。"""
    base = _REPO_ROOT / "src/ai_rpg_world/application/llm/services"
    assert not (base / relative_path).exists()


def test_production_prompt_builder_injects_ui_context() -> None:
    """本番のプロンプト構築はUI構築器を明示注入し、省略時の旧実装に頼らない。"""
    path = _REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py"
    calls = [
        node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "DefaultPromptBuilder"
    ]
    assert calls
    assert all(any(kw.arg == "ui_context_builder" for kw in call.keywords) for call in calls)
