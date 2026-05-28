"""create_llm_agent_wiring の physical_map_repository Optional 対応。

Issue #227 chore (tile-map 依存除去) PR-2:
    spot_graph 専用ランタイムでは physical_map_repository=None で
    wiring を組めることを保証する。tile 依存のツール (inspect_target 等) は
    None のとき executor 側でガードされるため、wiring 構築自体は成功する。
"""

import inspect

import pytest

from ai_rpg_world.application.llm.wiring import (
    create_llm_agent_wiring,
)
from ai_rpg_world.application.llm.wiring.spot_graph_wiring import (
    create_spot_graph_wiring,
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

    def test_create_spot_graph_wiring_physical_map_repository_has_default_none(
        self,
    ) -> None:
        """create_spot_graph_wiring の physical_map_repository が default=None。"""
        sig = inspect.signature(create_spot_graph_wiring)
        param = sig.parameters["physical_map_repository"]
        assert param.default is None
