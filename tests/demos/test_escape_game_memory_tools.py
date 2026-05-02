"""EscapeGameRuntime の memory_query / working_memory / TODO ツール実行。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WORKING_MEMORY_APPEND,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"


@pytest.fixture
def runtime():
    from demos.escape_game.escape_game_runtime import create_escape_game_runtime

    return create_escape_game_runtime(SCENARIO_PATH)


def test_memory_tools_are_exposed(runtime) -> None:
    names = [d.name for d in runtime.get_tool_definitions()]
    assert TOOL_NAME_MEMORY_QUERY in names
    assert TOOL_NAME_WORKING_MEMORY_APPEND in names
    assert TOOL_NAME_TODO_ADD in names


def test_working_memory_append_then_query(runtime) -> None:
    pid = PlayerId(runtime.scenario.player_spawns[0].player_id)
    add = runtime.run_llm_auxiliary_tool(
        pid,
        TOOL_NAME_WORKING_MEMORY_APPEND,
        {"text": "仮説: 受付の貼り紙は日付が消されている。"},
    )
    assert add.success
    q = runtime.run_llm_auxiliary_tool(
        pid,
        TOOL_NAME_MEMORY_QUERY,
        {"expr": "working_memory.take(5)", "output_mode": "text"},
    )
    assert q.success
    assert "仮説" in q.message or "受付" in q.message


def test_todo_add_then_list(runtime) -> None:
    pid = PlayerId(runtime.scenario.player_spawns[0].player_id)
    a = runtime.run_llm_auxiliary_tool(
        pid, TOOL_NAME_TODO_ADD, {"content": "通路の先を確認する"}
    )
    assert a.success
    lst = runtime.run_llm_auxiliary_tool(pid, TOOL_NAME_TODO_LIST, {})
    assert lst.success
    assert "通路" in lst.message
