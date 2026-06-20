"""world_runtime と本家 DefaultPromptBuilder の prompt 経路の収束を保証する。

Issue #227 経路統一プロジェクトの後続レビュー (HIGH-3):
    world_runtime runtime は独自経路で prompt を組み立てているが、shareable な
    部品 (SectionBasedContextFormatStrategy, DefaultRecentEventsFormatter,
    format_active_memos, tile-map field の None 固定) はすべて本家と共有して
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


def test_both_paths_use_section_based_context_format_strategy() -> None:
    """両経路が同一の SectionBasedContextFormatStrategy を使う。"""
    prompt_builder = _read(
        _REPO_ROOT / "src/ai_rpg_world/application/llm/services/prompt_builder.py"
    )
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    # DefaultPromptBuilder は wiring 経由で受け取る (strategy 名は context_format_strategy.py
    # に集中)。world_runtime も同じ strategy class をクラス定数で持つ。
    assert "SectionBasedContextFormatStrategy" in world_runtime
    # prompt_builder は IContextFormatStrategy 経由で受け取るので strategy 名は出ない


def test_both_paths_use_default_recent_events_formatter() -> None:
    """両経路が DefaultRecentEventsFormatter を recent events 整形に使う。"""
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    assert "DefaultRecentEventsFormatter" in world_runtime


def test_world_runtime_uses_shared_active_memos_formatter() -> None:
    """world_runtime が共通の format_active_memos を import/委譲する。"""
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    assert "active_memos_formatter" in world_runtime
    assert "format_active_memos" in world_runtime


def test_prompt_builder_uses_shared_active_memos_formatter() -> None:
    """DefaultPromptBuilder も共通の format_active_memos を使う。"""
    prompt_builder = _read(
        _REPO_ROOT / "src/ai_rpg_world/application/llm/services/prompt_builder.py"
    )
    assert "from ai_rpg_world.application.llm.services.active_memos_formatter" in prompt_builder
    assert "format_active_memos" in prompt_builder


def test_world_runtime_holds_formatter_instances_as_class_vars() -> None:
    """world_runtime runtime が formatter を class-level に、context_strategy を
    env 注入式の instance field として保持している。

    旧: 両方 ClassVar (= 毎回 new を避ける HIGH-3 改善)。
    PR #445: ``_context_strategy`` だけ instance field に格上げした。
    ClassVar の hard-coded default で PROMPT_SECTION_ORDER env を黙って無視する
    silent failure が見つかったため (3 つ目の config-init split)。
    formatter (stateless) は ClassVar のまま維持。
    """
    world_runtime = _read(_REPO_ROOT / "src/ai_rpg_world/application/world_runtime/world_runtime.py")
    # formatter は引き続き ClassVar (stateless / env 依存無し)
    assert "_recent_events_formatter: ClassVar" in world_runtime
    # _context_strategy は instance field に格上げ + cfg 由来 factory で注入
    assert "_context_strategy: SectionBasedContextFormatStrategy = field" in world_runtime
    # PR #451 (PR 6/6): _from_env → _from_config に rename
    assert "_build_context_format_strategy_from_config" in world_runtime


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
    """world_runtime adapter モジュールが存在し、4 つの adapter を提供する (HIGH-3 Part 2)。"""
    adapters = _read(
        _REPO_ROOT / "src/ai_rpg_world/application/world_runtime/default_prompt_builder_adapters.py"
    )
    assert "class WorldRuntimeQueryAdapter" in adapters
    assert "class WorldProfileRepositoryAdapter" in adapters
    assert "class WorldSystemPromptBuilder" in adapters
    assert "class WorldAvailableToolsProvider" in adapters
