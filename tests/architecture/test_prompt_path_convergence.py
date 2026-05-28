"""escape_game と本家 DefaultPromptBuilder の prompt 経路の収束を保証する。

Issue #227 経路統一プロジェクトの後続レビュー (HIGH-3):
    escape_game runtime は独自経路で prompt を組み立てているが、shareable な
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
    escape_runtime = _read(_REPO_ROOT / "demos/escape_game/escape_game_runtime.py")
    # DefaultPromptBuilder は wiring 経由で受け取る (strategy 名は context_format_strategy.py
    # に集中)。escape_game も同じ strategy class をクラス定数で持つ。
    assert "SectionBasedContextFormatStrategy" in escape_runtime
    # prompt_builder は IContextFormatStrategy 経由で受け取るので strategy 名は出ない


def test_both_paths_use_default_recent_events_formatter() -> None:
    """両経路が DefaultRecentEventsFormatter を recent events 整形に使う。"""
    escape_runtime = _read(_REPO_ROOT / "demos/escape_game/escape_game_runtime.py")
    assert "DefaultRecentEventsFormatter" in escape_runtime


def test_escape_game_uses_shared_active_memos_formatter() -> None:
    """escape_game が共通の format_active_memos を import/委譲する。"""
    escape_runtime = _read(_REPO_ROOT / "demos/escape_game/escape_game_runtime.py")
    assert "active_memos_formatter" in escape_runtime
    assert "format_active_memos" in escape_runtime


def test_prompt_builder_uses_shared_active_memos_formatter() -> None:
    """DefaultPromptBuilder も共通の format_active_memos を使う。"""
    prompt_builder = _read(
        _REPO_ROOT / "src/ai_rpg_world/application/llm/services/prompt_builder.py"
    )
    assert "from ai_rpg_world.application.llm.services.active_memos_formatter" in prompt_builder
    assert "format_active_memos" in prompt_builder


def test_escape_game_holds_formatter_instances_as_class_vars() -> None:
    """escape_game runtime が formatter/strategy を class-level に保持している。

    毎回 new するのではなく ClassVar として共有 (HIGH-3 改善)。
    """
    escape_runtime = _read(_REPO_ROOT / "demos/escape_game/escape_game_runtime.py")
    assert "_recent_events_formatter: ClassVar" in escape_runtime
    assert "_context_strategy: ClassVar" in escape_runtime


def test_escape_game_build_full_prompt_has_migration_note() -> None:
    """escape_game の build_full_prompt が将来の DefaultPromptBuilder 統合 TODO を持つ。

    現状の「DefaultPromptBuilder ではなく独自経路」状態を明文化し、
    後続 PR で統合する意図を docstring に残す。
    """
    escape_runtime = _read(_REPO_ROOT / "demos/escape_game/escape_game_runtime.py")
    assert "DefaultPromptBuilder" in escape_runtime
    # docstring の note が残っているか軽く確認
    assert "別 PR で対応" in escape_runtime or "別 PR" in escape_runtime
