"""``get_memory_specs`` の有効化フラグ別の expose 挙動 (Phase 1a, 1d)。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
    TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
)


def _names(specs):
    return [d.name for d, _ in specs]


class TestGetMemorySpecsFlags:
    """flag が False のときは tool が出ない / True のときだけ出る。"""

    def test_default_は_全部_OFF(self) -> None:
        names = _names(get_memory_specs())
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED not in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC not in names

    def test_episodic_explore_related_enabled_True_で_だけ_出る(self) -> None:
        names = _names(get_memory_specs(episodic_explore_related_enabled=True))
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC not in names

    def test_semantic_search_enabled_True_で_だけ_出る(self) -> None:
        names = _names(get_memory_specs(semantic_search_enabled=True))
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in names
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED not in names

    def test_両方_True_なら_両方_出る(self) -> None:
        names = _names(
            get_memory_specs(
                episodic_explore_related_enabled=True,
                semantic_search_enabled=True,
            )
        )
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in names

    def test_memo_enabled_と_combinable(self) -> None:
        """memo 系と semantic search は同時に有効化できる。"""
        specs = get_memory_specs(memo_enabled=True, semantic_search_enabled=True)
        names = _names(specs)
        assert "memo_add" in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in names
