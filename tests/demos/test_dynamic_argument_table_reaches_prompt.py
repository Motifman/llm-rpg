"""動的引数候補表が、本番の行動選択プロンプト末尾へ届くことを保証する。"""

from __future__ import annotations

import copy

from tests.demos._world_runtime_helpers import create_world_runtime_session

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _CapturingClient(StubLlmClient):
    """実行せず、Phase A が実際に渡したメッセージだけを保持する。"""

    def __init__(self) -> None:
        super().__init__({"name": "wait", "arguments": {}})
        self.messages: list[dict] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.messages = copy.deepcopy(messages)
        return super().invoke(messages, tools, tool_choice, **kwargs)


def test_runtime_places_copyable_candidates_before_the_final_instruction(
    monkeypatch, tmp_path
) -> None:
    """現在地の説明とは別に、実引数名と候補値を行動指示の直前へ集約する。"""
    client = _CapturingClient()
    state = create_world_runtime_session(monkeypatch, tmp_path, stub=client)
    player_id = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))

    phase_a = state.llm_wiring.run_phase_a(player_id)

    user = client.messages[-1]["content"]
    table = phase_a.prompt["dynamic_argument_candidates"]["rendered"]
    instruction = phase_a.prompt["action_instruction"]
    assert table
    assert user.endswith(instruction)
    assert user.count("【現在選べる対象引数】") == 1
    assert user.index(table) < user.index(instruction)
    assert "travel_to.destination_label" in table
    assert "interact.target_label" in table
