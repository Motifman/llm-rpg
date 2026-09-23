"""存在しない tool 名への失敗文は、そのターンに送った tool だけを勧める (#1413)。

## handler 表から作ると、出していない tool を勧める

失敗文の「現在使える tool」は ``_tool_handlers`` の全キーから作っていた。会議中に
送った tool は 7 個なのに、失敗文には ``interact`` や ``attack``、この世界で出して
いない ``memory_*`` まで 33 個が並んでいた。勧められた名前を次のターンに呼ぶと、
今度は「いまは選べない」で落ちる。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    offered_tools_from_payload,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)


class _StubClient:
    """LLM は呼ばない。dispatch だけを見る。"""


def _wiring(runtime) -> _WorldLlmWiring:
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_StubClient(),
    )


def _listed_tools(message: str) -> set[str]:
    found = re.search(r"現在使える tool: \[(.*)\]", message)
    assert found is not None, message
    return {name.strip() for name in found.group(1).split(",") if name.strip()}


@pytest.fixture()
def in_a_meeting():
    runtime = create_world_runtime(_DRILL)
    runtime.call_emergency_meeting(_MORI)
    wiring = _wiring(runtime)
    offered = offered_tools_from_payload(wiring._build_tools_payload(_MORI))
    assert "interact" not in offered
    return wiring, offered


class TestTheFailureListsOnlyTheOfferedTools:
    """UNSUPPORTED_TOOL の失敗文が、そのターンに送った tool だけから作られることを保証する。"""

    def test_the_listed_tools_are_exactly_the_offered_ones_during_a_meeting(
        self, in_a_meeting
    ) -> None:
        """会議中に存在しない名前を呼ぶと、一覧は送った tool と一致し、interact は載らない。"""
        wiring, offered = in_a_meeting

        result = wiring._execute_tool(
            _MORI, "gather", {}, None, offered_tools_at_prompt=offered
        )

        assert result.error_code == "UNSUPPORTED_TOOL"
        assert _listed_tools(result.message) == set(offered)

    def test_a_name_close_to_a_hidden_tool_is_not_suggested(self, in_a_meeting) -> None:
        """会議中に interact の短縮形を呼んでも、送っていない interact を提案しない。

        **正の対照**: 会議の外では同じ名前に interact を提案する。
        """
        wiring, offered = in_a_meeting

        result = wiring._execute_tool(
            _MORI, "spot_graph_interact", {}, None, offered_tools_at_prompt=offered
        )

        assert "もしかして" not in result.message

    def test_outside_a_meeting_the_same_name_is_suggested(self) -> None:
        """会議の外では、送った一覧に interact があるので提案する (上の試験の対照)。"""
        runtime = create_world_runtime(_DRILL)
        wiring = _wiring(runtime)
        offered = offered_tools_from_payload(wiring._build_tools_payload(_MORI))

        result = wiring._execute_tool(
            _MORI, "spot_graph_interact", {}, None, offered_tools_at_prompt=offered
        )

        assert "もしかして 'interact' ですか?" in result.message
