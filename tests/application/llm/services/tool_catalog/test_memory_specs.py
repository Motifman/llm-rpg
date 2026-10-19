"""``get_memory_specs`` が引数ごとに出す道具を保証する。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
)


def _names(specs):
    return [d.name for d, _ in specs]


class TestGetMemorySpecsFlags:
    """引数で有効にした道具だけが出て、既定ではどれも出ないことを保証する。"""

    def test_default_returns_no_tools(self) -> None:
        """引数を渡さないとき、道具を 1 つも返さない。"""
        assert get_memory_specs() == []

    def test_episode_recall_max_handles_exposes_episode_recall(self) -> None:
        """episode_recall_max_handles を渡すと episode_recall を出す。"""
        names = _names(get_memory_specs(episode_recall_max_handles=3))

        assert names == [TOOL_NAME_EPISODE_RECALL]

    def test_episode_index_revision_enabled_exposes_revise_index(self) -> None:
        """episode_index_revision_enabled=True のとき episode_revise_index を出す。"""
        names = _names(get_memory_specs(episode_index_revision_enabled=True))

        assert names == [TOOL_NAME_EPISODE_REVISE_INDEX]
