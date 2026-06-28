"""脱出ランタイムでは恒久的に未対応な tool を LLM に見せないことを保証する。

PR-A (Issue #621 後続): ``spot_graph_set_sub_location`` は escape runtime で
``_handle_set_sub_location`` が常に ``UNSUPPORTED_TOOL`` を返す。それにも
かかわらず tool catalog 経由で LLM に expose されており、Y_after_issue621
trace では 3 回叩かれて全部失敗していた。LLM 側に見せないようにする。

handler 自体は防御として残す (= 何らかの経路で呼ばれても安全に失敗する) が、
tool list には出さない設計。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    filter_definitions_for_escape_llm,
    ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS,
)


class _FakeDef:
    """`ToolDefinitionDto` の name 属性だけを使うので最小 stub。"""

    def __init__(self, name: str) -> None:
        self.name = name


class TestExcludeSet:
    def test_set_sub_location_は_除外対象に含まれる(self) -> None:
        """脱出ランタイムでは set_sub_location は恒久的に UNSUPPORTED_TOOL を
        返す仕様のため、LLM に見せる必要が無い。"""
        assert (
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION
            in ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS
        )

    def test_他の_spot_graph_系_tool_は_除外対象に含まれない(self) -> None:
        """主要 tool が誤って除外されていないことの regression check。"""
        for name in (
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_WAIT,
        ):
            assert name not in ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS


class TestFilterFunction:
    def test_除外対象を_除いた_definition_list_を_返す(self) -> None:
        """脱出ランタイムが LLM に渡す tool 一覧 (= ``tools_payload``) を
        生成する時に呼ばれるフィルタ。除外対象を取り除き、それ以外は順序を
        保ったまま通す。"""
        defs = [
            _FakeDef(TOOL_NAME_SPOT_GRAPH_EXPLORE),
            _FakeDef(TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION),
            _FakeDef(TOOL_NAME_SPOT_GRAPH_TRAVEL_TO),
            _FakeDef(TOOL_NAME_SPOT_GRAPH_WAIT),
        ]
        result = filter_definitions_for_escape_llm(defs)
        names = [d.name for d in result]
        assert names == [
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_WAIT,
        ]

    def test_空_list_は_空_list_を_返す(self) -> None:
        assert filter_definitions_for_escape_llm([]) == []

    def test_全部_除外対象なら_空_list(self) -> None:
        defs = [_FakeDef(TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION)]
        assert filter_definitions_for_escape_llm(defs) == []

    def test_除外対象が_無ければ_そのまま_返す(self) -> None:
        defs = [
            _FakeDef(TOOL_NAME_SPOT_GRAPH_EXPLORE),
            _FakeDef(TOOL_NAME_SPOT_GRAPH_TRAVEL_TO),
        ]
        assert filter_definitions_for_escape_llm(defs) == defs
