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
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
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

    def do_explore(
        self,
        player_id: PlayerId,
        *,
        expected_result=None,
        intention=None,
        emotion_hint=None,
    ) -> _ExploreResult:
        # U2: runtime_manager の handler が subjective fields を渡すようになったため、
        # fake も実 runtime と同じ optional kwargs を受ける (値はこのテストでは未使用)。
        self.explore_calls.append(player_id.value)
        result = _ExploreResult()
        desc = " / ".join(result.discovery_descriptions)
        self._record_action_result(
            player_id,
            "explore_sub_locations()",
            f"発見: {desc}" if desc else "新しい発見はなかった",
        )
        return result

    def _record_action_result(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        *,
        tool_name: str = "",
        success: bool = True,
        error_code: str | None = None,
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
            {
                "name": "spot_graph_explore",
                "arguments": {"inner_thought": "足元の砂埃に気をつけながら、部屋の隅々まで見回す。"},
            }
        ),
    )

    wiring.llm_turn_trigger.schedule_turn(PlayerId(1))
    wiring.llm_turn_trigger.run_scheduled_turns()

    assert runtime.explore_calls == [1]
    assert runtime.action_results
    assert any("古いメモ" in r[2] for r in runtime.action_results)


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
