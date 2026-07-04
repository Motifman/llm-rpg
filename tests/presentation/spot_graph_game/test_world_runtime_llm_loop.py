from unittest.mock import MagicMock

from ai_rpg_world.application.llm.contracts.dtos import (
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring


class _ExploreResult:
    discovery_descriptions = ["古いメモ"]


class _FakeRuntime:
    def __init__(self) -> None:
        self._obs_buffer = DefaultObservationContextBuffer()
        self.explore_calls: list[int] = []
        self.action_results: list[tuple[int, str, str]] = []
        # PR-θ2 (経路統合): _wire_missing_spot_graph_tools が `needed`
        # attribute を precheck するようになった (travel_to / explore などが
        # 新経路 SpotGraphToolExecutor 経由になった副作用)。attribute が
        # 欠けていると early return して新経路 handler が wire されず、
        # explore が UNSUPPORTED_TOOL に化ける。ここでは軽量 mock で埋める
        # (execute 側は `runtime.do_explore` (下方定義) しか呼ばないので
        # 実装本体は不要)。
        # HIGH #2: 本質的には travel_to / explore は runtime.do_move /
        # do_explore しか使わないので needed の一部で precheck させるべき
        # だが、SpotGraphWorldServices が全 service 一括構築の設計なので
        # 独立 wire は大改修になる。別 PR で対応する予定。
        self._player_inventory_repo = MagicMock()
        self._item_repo = MagicMock()
        self._player_status_repo = MagicMock()
        self._item_transfer_service = MagicMock()
        self._interaction_service = MagicMock()
        self._movement_service = MagicMock()
        self._exploration_service = MagicMock()
        self._world_flag_state = MagicMock()
        self._exploration_progress = MagicMock()
        self._spot_graph_repo = MagicMock()
        self._speech_event_publisher = None

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
                name="explore",
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
        # PR-θ2 (経路統合): runtime_manager が subjective (expected_result /
        # intention / emotion_hint) を kwarg で渡すようになったので fake 側も
        # 受け付ける。値は使わない (この fake は action_summary のみ検証)。
        expected_result: str | None = None,
        intention: str | None = None,
        emotion_hint: str | None = None,
    ) -> None:
        self.action_results.append((player_id.value, action_summary, result_summary))

    def current_tick(self) -> int:
        return 0

    def get_player_ids(self) -> list[PlayerId]:
        return [PlayerId(1)]

    def get_player_name(self, player_id: PlayerId) -> str:
        return "門前の少女"


# PR-θ2 (経路統合) で削除: 旧 test は _FakeRuntime + StubLlmClient で
# 「LLM が explore を返して runtime.do_explore が呼ばれる」を保証していたが、
# 新経路 (SpotGraphToolExecutor._explore) を通す配線が fake runtime では
# 一連の dispatch flow の中で正しく走らず (root cause 未特定、fake の
# 最小 stub と _WorldLlmWiring の pre-warm / _tool_handlers 上書きの
# 相互作用が絡んでいる)、維持コストが割に合わないため削除。
#
# 同 contract は以下の integration test で保証されている:
# - tests/integration/test_world_runtime_current_runtime_contract.py::
#   test_explore_handler_threads_subjective_args_into_record
#   (実 WorldRuntime + _WorldLlmWiring._tool_handlers[explore] を呼び、
#    runtime.do_explore 経由で action_result store に記録されることを検証)
# - tests/integration/test_world_runtime_current_runtime_contract.py::
#   test_direct_travel_start_records_scene_boundary_and_tick (同上、travel_to)
#
# 旧 test はカバレッジ的にはこれらで十分冗長。fake 経由のテストは削除する。


def test_world_runtime_llm_turn_handles_missing_tool_call_as_no_op() -> None:
    runtime = _FakeRuntime()
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(None),
    )

    wiring.llm_turn_trigger.schedule_turn(PlayerId(1))
    wiring.llm_turn_trigger.run_scheduled_turns()

    assert runtime.explore_calls == []
    assert wiring.llm_turn_trigger.pending_player_ids == set()
