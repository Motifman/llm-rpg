"""ランタイムが、実際に出すツールの一覧から Being の道具を拾い、作法をそこから作ることを保証する (design_decisions D1630-6)。"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import pytest
from tests.runtime_config_helpers import runtime_config

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.contract import OfferedBeingTools

_MINE_VILLAGE = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "mine_village_v1.json"


@pytest.fixture(autouse=True)
def _quiet(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.CRITICAL)


class TestOfferedBeingTools:
    """出すツールの一覧と、Being の道具と、システムプロンプトの作法の関係を保証する。"""

    def test_mine_village_offers_every_being_tool(self) -> None:
        """廃坑の山村は、独白とメモの引数、episode_recall、目次をすべて出す。"""
        runtime = create_world_runtime(_MINE_VILLAGE, config=runtime_config())

        assert runtime.offered_being_tools() == OfferedBeingTools(
            inner_thought="inner_thought", memo="memo", episode_recall="episode_recall", episode_index_shown=True
        )

    def test_tools_are_read_from_the_offered_tool_definitions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """出すツールの一覧から episode_recall の tool と、memo と inner_thought の引数を除くと、その 3 つは道具に入らない。"""
        runtime = create_world_runtime(_MINE_VILLAGE, config=runtime_config())
        offered = runtime.get_tool_definitions(for_every_player=True)
        without = [
            replace(d, parameters={**d.parameters, "properties": _without_memo(d.parameters.get("properties", {}))})
            for d in offered
            if d.name != "episode_recall"
        ]
        monkeypatch.setattr(runtime, "get_tool_definitions", lambda **_: without)

        tools = runtime._being_tools_offered_now()

        assert (tools.inner_thought, tools.memo, tools.episode_recall) == (None, None, None)
        assert tools.episode_index_shown is True


def _without_memo(properties: dict) -> dict:
    return {name: value for name, value in properties.items() if name not in ("memo", "inner_thought")}
