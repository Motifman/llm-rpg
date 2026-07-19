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

    def test_default_all_off(self) -> None:
        """default は全部 OFF。"""
        names = _names(get_memory_specs())
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED not in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC not in names

    def test_episodic_explore_related_enabled_true_rendered(self) -> None:
        """episodicexplorerelatedenabledTrue でだけ出る。"""
        names = _names(get_memory_specs(episodic_explore_related_enabled=True))
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC not in names

    def test_semantic_search_enabled_true_rendered(self) -> None:
        """semanticsearchenabledTrue でだけ出る。"""
        names = _names(get_memory_specs(semantic_search_enabled=True))
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in names
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED not in names

    def test_true_rendered(self) -> None:
        """両方 True なら 両方 出る。"""
        names = _names(
            get_memory_specs(
                episodic_explore_related_enabled=True,
                semantic_search_enabled=True,
            )
        )
        assert TOOL_NAME_MEMORY_EXPLORE_RELATED in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in names

    def test_memo_enabled_combinable(self) -> None:
        """memo 系と semantic search は同時に有効化できる。"""
        specs = get_memory_specs(memo_enabled=True, semantic_search_enabled=True)
        names = _names(specs)
        assert "memo_add" in names
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in names


class TestRecallByHandleSpec:
    """afterglow 用の能動想起ツールが flag で expose されることを保証する。"""

    def test_disabled_by_default(self) -> None:
        """flag 未指定なら memory_recall_by_handle は spec に出ない (= default off)。"""
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
        )

        names = _names(get_memory_specs())
        assert TOOL_NAME_MEMORY_RECALL_BY_HANDLE not in names

    def test_recall_by_handle_enabled_exposes_the_tool(self) -> None:
        """``recall_by_handle_enabled=True`` で expose される。
        afterglow の見出しから本文を引き戻す経路を LLM に見せる前提。"""
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
        )

        names = _names(get_memory_specs(recall_by_handle_enabled=True))
        assert TOOL_NAME_MEMORY_RECALL_BY_HANDLE in names

    def test_tool_description_mentions_afterglow_section(self) -> None:
        """LLM が prompt の「【さっき思い出した記憶の見出し】」と本ツールを
        繋げて理解できるよう、description にその section 名と handle 形式
        (``ep_``) が明示されていること。"""
        from ai_rpg_world.application.llm.services.tool_catalog.memory import (
            MEMORY_RECALL_BY_HANDLE_DEFINITION,
        )

        desc = MEMORY_RECALL_BY_HANDLE_DEFINITION.description
        assert "さっき思い出した記憶の見出し" in desc
        assert "ep_" in desc
