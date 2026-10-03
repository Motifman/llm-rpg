"""ゲームのツール呼び出しとシナリオを、エージェントの 1 手と環境に入るときの取り決めへ変換する。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ai_rpg_world.being.contract import AgentMove, EnvironmentEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.scenario.models import ScenarioLoadResult


def agent_move_from_tool_call(
    tool_name: str, arguments: Mapping[str, Any], *, call_id: str
) -> AgentMove:
    remaining = dict(arguments)
    expectation = _pop_text(remaining, "expected_result")
    inner_thought = _pop_text(remaining, "inner_thought")
    goal_update = _pop_text(remaining, "goal_update")
    return AgentMove(
        call_id=call_id,
        tool_name=tool_name,
        arguments=remaining,
        expectation=expectation,
        inner_thought=inner_thought,
        goal_update=goal_update,
    )


def environment_entry_for_player(
    scenario: ScenarioLoadResult, player_id: PlayerId
) -> EnvironmentEntry:
    spawn = next(
        (s for s in scenario.player_spawns if s.player_id == player_id.value), None
    )
    if spawn is None:
        raise LookupError(f"player {player_id.value} is not in the scenario")
    goal = (spawn.objective or scenario.metadata.llm_objective_text or "").strip()
    return EnvironmentEntry(
        environment_name=scenario.metadata.title,
        self_name=spawn.name,
        imposed_goal=goal or None,
    )


def _pop_text(arguments: dict[str, Any], name: str) -> str | None:
    value = arguments.pop(name, None)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be str or null, got {type(value).__name__}")
    return value if value.strip() else None
