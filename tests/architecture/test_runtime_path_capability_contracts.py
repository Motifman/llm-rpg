"""Runtime path capability contracts.

These tests intentionally freeze the current runtime path contract:

- ``escape_game`` runtime used by experiments/server sessions
- retired spot-graph full wiring
- generic LLM agent wiring that still carries tile-map compatibility

If one of these assertions fails, update the capability matrix deliberately in
the same PR that changes the runtime wiring. The goal is to prevent silent
drift between the code and the team's shared mental model.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import fields
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_experiment_and_server_entrypoints_use_escape_game_runtime() -> None:
    """The experiment/server path is still GameRuntimeManager -> escape_game."""
    experiment = _read(_REPO_ROOT / "scripts/run_scenario_experiment.py")
    app = _read(_SRC / "ai_rpg_world/presentation/spot_graph_game/app.py")
    manager = _read(_SRC / "ai_rpg_world/presentation/spot_graph_game/runtime_manager.py")

    assert "GameRuntimeManager" in experiment
    assert "GameRuntimeManager" in app
    assert "create_escape_game_runtime" in manager
    assert "create_spot_graph_wiring" not in experiment


def test_escape_game_memory_stack_has_flag_gated_semantic_extension() -> None:
    """escape_game's episodic builder now exposes semantic/link handles behind flags."""
    from ai_rpg_world.application.llm.wiring.episodic_stack import (
        EpisodicStack,
        build_episodic_stack,
    )

    stack_fields = {field.name for field in fields(EpisodicStack)}
    build_params = inspect.signature(build_episodic_stack).parameters

    assert {
        "chunk_coordinator",
        "passive_recall",
        "noun_matcher",
        "episode_store",
        "semantic_passive_recall",
        "semantic_passive_top_k",
        "episodic_semantic_promotion",
        "semantic_memory_store",
        "memory_link_store",
    } <= stack_fields
    assert build_params["semantic_enabled"].default is False
    assert build_params["semantic_passive_top_k"].default == 0
    assert "semantic_gist_service" in build_params
    assert "semantic_persona_resolver" in build_params


def test_generic_llm_agent_wiring_remains_tile_map_compatible() -> None:
    """Only the generic wiring still accepts tile-map dependencies."""
    from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring

    sig = inspect.signature(create_llm_agent_wiring)
    assert "physical_map_repository" in sig.parameters
    assert sig.parameters["physical_map_repository"].default is None

    generic = _read(_SRC / "ai_rpg_world/application/llm/wiring/__init__.py")
    assert "include_tile_movement: bool = True" in generic
    assert "tile_map_enabled: bool = True" in generic


def test_spot_graph_full_wiring_is_retired() -> None:
    """spot_graph full wiring is no longer an exported runtime path."""
    spot_graph_wiring = _SRC / "ai_rpg_world/application/llm/wiring/spot_graph_wiring.py"
    assert not spot_graph_wiring.exists()

    wiring_pkg = importlib.import_module("ai_rpg_world.application.llm.wiring")
    assert not hasattr(wiring_pkg, "create_spot_graph_wiring")
    assert "create_spot_graph_wiring" not in getattr(wiring_pkg, "__all__", ())


def test_memory_recall_episodes_is_escape_game_specific() -> None:
    """Active episode recall is wired in escape_game."""
    escape_runtime = _read(
        _SRC / "ai_rpg_world/application/escape_game/escape_game_runtime.py"
    )
    runtime_manager = _read(
        _SRC / "ai_rpg_world/presentation/spot_graph_game/runtime_manager.py"
    )

    assert "memory_recall_episodes" in escape_runtime
    assert "TOOL_NAME_MEMORY_RECALL_EPISODES" in runtime_manager
