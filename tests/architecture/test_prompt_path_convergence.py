"""world_runtime と本家 DefaultPromptBuilder の prompt 経路の収束を保証する。

Issue #227 経路統一プロジェクトの後続レビュー (HIGH-3):
    world_runtime runtime は独自経路で prompt を組み立てているが、shareable な
    部品 (作業記憶、DefaultRecentEventsFormatter、
    tile-map field の None 固定) はすべて本家と共有して
    いる。完全な経路統一は別 PR で行うが、現在の収束状態が後退しないことを
    本ファイルが構造的に固定する。

落ちる assertion はすべて「経路の再 drift」を意味するため、慎重に意図を
確認すること。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_prompt_builder_composes_from_the_working_memory() -> None:
    """DefaultPromptBuilder は区画を自分で並べず、Being の作業記憶から文を組む (#1630)。"""
    prompt_builder = _read(_REPO_ROOT / "src/ai_rpg_world/application/llm/services/prompt_builder.py")
    assert "CurrentWorkingMemory" in prompt_builder
    assert "message_text(memory)" in prompt_builder
    assert not (_REPO_ROOT / "src/ai_rpg_world/application/llm/services/context_format_strategy.py").exists()


def test_both_paths_use_default_recent_events_formatter() -> None:
    """両経路が DefaultRecentEventsFormatter を recent events 整形に使う。"""
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    assert "DefaultRecentEventsFormatter" in world_runtime


def test_world_runtime_holds_formatter_instances_as_class_vars() -> None:
    """world_runtime runtime が formatter を class-level に保持している。"""
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    # formatter は引き続き ClassVar (stateless / env 依存無し)
    assert "_recent_events_formatter: ClassVar" in world_runtime


def test_world_runtime_build_full_prompt_uses_default_prompt_builder() -> None:
    """world_runtime の build_full_prompt が本家 DefaultPromptBuilder.build に統合済み。

    Issue #227 後続 HIGH-3 Part 2 で完了。runtime は adapter 経由で
    DefaultPromptBuilder を構築し、build_full_prompt はそれを呼ぶだけになっている。
    """
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    # 統合の証跡: _get_or_build_default_prompt_builder 経由で builder を構築している
    assert "_get_or_build_default_prompt_builder" in world_runtime
    assert "DefaultPromptBuilder" in world_runtime


def test_world_runtime_default_prompt_builder_adapters_module_exists() -> None:
    """world_runtime adapter モジュールが存在し、現在状態とツールの一覧の 2 つの adapter を提供する (HIGH-3 Part 2)。

    システムプロンプトとプロフィールの adapter は、作業記憶から組むようにして消した (#1630)。
    """
    adapters = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/default_prompt_builder_adapters.py")
    assert "class WorldRuntimeQueryAdapter" in adapters
    assert "class WorldAvailableToolsProvider" in adapters
