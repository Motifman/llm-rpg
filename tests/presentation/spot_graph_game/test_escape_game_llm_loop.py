from ai_rpg_world.application.llm.contracts.dtos import (
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _EscapeGameLlmWiring


class _ExploreResult:
    discovery_descriptions = ["古いメモ"]


class _FakeRuntime:
    def __init__(self) -> None:
        self._obs_buffer = DefaultObservationContextBuffer()
        self.explore_calls: list[int] = []
        self.action_results: list[tuple[int, str, str]] = []

    def build_full_prompt(self, player_id: PlayerId) -> dict:
        return {
            "system": "system",
            "user": "user",
            "tool_runtime_context": ToolRuntimeContextDto.empty(),
        }

    def get_tool_definitions(self) -> list[ToolDefinitionDto]:
        return [
            ToolDefinitionDto(
                name="spot_graph_explore",
                description="explore",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ]

    def do_explore(self, player_id: PlayerId) -> _ExploreResult:
        self.explore_calls.append(player_id.value)
        return _ExploreResult()

    def _record_action_result(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
    ) -> None:
        self.action_results.append((player_id.value, action_summary, result_summary))

    def current_tick(self) -> int:
        return 0

    def get_player_ids(self) -> list[PlayerId]:
        return [PlayerId(1)]

    def get_player_name(self, player_id: PlayerId) -> str:
        return "門前の少女"


def test_escape_game_llm_turn_executes_returned_tool() -> None:
    runtime = _FakeRuntime()
    wiring = _EscapeGameLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(
            {"name": "spot_graph_explore", "arguments": {}}
        ),
    )

    wiring.llm_turn_trigger.schedule_turn(PlayerId(1))
    wiring.llm_turn_trigger.run_scheduled_turns()

    assert runtime.explore_calls == [1]
    assert runtime.action_results
    assert "古いメモ" in runtime.action_results[0][2]


def test_escape_game_llm_turn_handles_missing_tool_call_as_no_op() -> None:
    runtime = _FakeRuntime()
    wiring = _EscapeGameLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(None),
    )

    wiring.llm_turn_trigger.schedule_turn(PlayerId(1))
    wiring.llm_turn_trigger.run_scheduled_turns()

    assert runtime.explore_calls == []
    assert wiring.llm_turn_trigger.pending_player_ids == set()
