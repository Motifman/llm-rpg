"""create_llm_agent_wiring の physical_map_repository Optional 対応。

Issue #227 chore (tile-map 依存除去) PR-2:
    generic wiring は physical_map_repository=None でも組めることを保証する。
    tile 依存のツール (inspect_target 等) は None のとき executor 側でガード
    されるため、wiring 構築自体は成功する。
"""

import inspect

import pytest

from ai_rpg_world.application.llm.wiring import (
    create_llm_agent_wiring,
)


class TestPhysicalMapRepositoryIsOptional:
    """シグネチャ上 physical_map_repository が Optional になっている。"""

    def test_create_llm_agent_wiring_physical_map_repository_has_default_none(
        self,
    ) -> None:
        """create_llm_agent_wiring の physical_map_repository が default=None。"""
        sig = inspect.signature(create_llm_agent_wiring)
        param = sig.parameters["physical_map_repository"]
        assert param.default is None
