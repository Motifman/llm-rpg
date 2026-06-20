# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p7")
"""LlmAgentOrchestrator のエピソード保存境界（tool 実行後にチャンク協調が保存する）の検証。"""

from typing import Any, Dict
from unittest.mock import patch

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    ChunkBoundaryDecision,
    ChunkBoundaryReason,
)

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IPromptBuilder,
    IToolArgumentResolver,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubPromptBuilder(IPromptBuilder):
    def __init__(self, *, runtime_context: ToolRuntimeContextDto | None = None) -> None:
        self._rtc = runtime_context or ToolRuntimeContextDto.empty()

    def build(
        self,
        player_id: PlayerId,
        action_instruction: str | None = None,
    ) -> dict[str, Any]:
        return {
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": TOOL_NAME_NO_OP, "description": "", "parameters": {}},
                },
                {
                    "type": "function",
                    "function": {
                        "name": "spot_graph_interact",
                        "description": "",
                        "parameters": {},
                    },
                },
            ],
            "tool_choice": "required",
            "tool_runtime_context": self._rtc,
        }


class _FailingResolver(IToolArgumentResolver):
    def resolve(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        raise ToolArgumentResolutionException("ラベルが解決できません", "INVALID_TARGET_LABEL")


def _orchestrator_with_episode(
    *,
    llm_client: StubLlmClient,
    mapper: ToolCommandMapper,
    resolver: IToolArgumentResolver | None = None,
) -> tuple[LlmAgentOrchestrator, InMemorySubjectiveEpisodeStore]:
    # Phase 3 Step 3e-3: episode_store は being_id 経路のみ。Resolver+WorldId を
    # ChunkCoordinator に注入する (= module-level ``being_id`` が "being_w1_p1"
    # なので player_id=1 用に Being を provision する)
    from ai_rpg_world.application.being.being_provisioning_service import (
        BeingProvisioningService,
    )
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import (
        DEFAULT_SINGLE_WORLD_ID,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
        InMemoryBeingRepository,
    )

    episode_store = InMemorySubjectiveEpisodeStore()
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory(max_entries_per_player=10)
    action_store = DefaultActionResultStore(max_entries_per_player=10)
    _being_repo = InMemoryBeingRepository()
    _resolver = BeingAttachmentResolver(_being_repo)
    # 各テストが異なる player_id を使う可能性に備えて 1〜10 まで provision
    _provisioning = BeingProvisioningService(_being_repo)
    for _pid in range(1, 11):
        _provisioning.ensure_attached(PlayerId(_pid))
    coordinator = EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding,
        action_result_store=action_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
        being_attachment_resolver=_resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
    )
    orch = LlmAgentOrchestrator(
        prompt_builder=_StubPromptBuilder(),
        llm_client=llm_client,
        tool_command_mapper=mapper,
        action_result_store=action_store,
        tool_argument_resolver=resolver,
        episodic_chunk_coordinator=coordinator,
    )
    return orch, episode_store


class TestOrchestratorEpisodicActionCapture:
    """tool_command_mapper.execute 通過後にチャンク経由で主観エピソードが保存されること。"""

    _CLOSE_CHUNK = ChunkBoundaryDecision(
        should_close_chunk=True,
        episode_generation_allowed_if_closed=True,
        reason=ChunkBoundaryReason.SEGMENT_EXPLICIT,
    )

    def test_tool_success_persists_episode(self) -> None:
        """成功した tool 結果が、チャンク閉鎖時にエピソードストアに 1 件入る。"""
        mapper = ToolCommandMapper(
            handler_map={
                TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(
                    success=True, message="何もしませんでした。", was_no_op=True
                )
            }
        )
        orch, store = _orchestrator_with_episode(
            llm_client=StubLlmClient(
                tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}}
            ),
            mapper=mapper,
        )
        with patch(
            "ai_rpg_world.application.llm.services.episodic_chunk_coordinator.decide_chunk_boundary",
            return_value=self._CLOSE_CHUNK,
        ):
            orch.run_turn(PlayerId(7))
        recent = store.list_recent_by_being(being_id, 10)
        assert len(recent) == 1
        assert recent[0].player_id == 7
        assert recent[0].action is not None
        assert recent[0].action.tool_name == TOOL_NAME_NO_OP

    def test_tool_failure_still_persists_episode(self) -> None:
        """tool 実行が失敗 DTO でもエピソードは保存する（予測誤差記録の前提）。"""

        def _fail(_pid: int, _args: dict) -> LlmCommandResultDto:
            return LlmCommandResultDto(
                success=False,
                message="罠が発動した。",
                error_code="TRAP_TRIGGERED",
            )

        mapper = ToolCommandMapper(handler_map={TOOL_NAME_NO_OP: _fail})
        orch, store = _orchestrator_with_episode(
            llm_client=StubLlmClient(
                tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}}
            ),
            mapper=mapper,
        )
        with patch(
            "ai_rpg_world.application.llm.services.episodic_chunk_coordinator.decide_chunk_boundary",
            return_value=self._CLOSE_CHUNK,
        ):
            orch.run_turn(PlayerId(2))
        # player_id=2 用の being_id で検証
        being_id_2 = _MIG_BeingId("being_w1_p2")
        assert len(store.list_recent_by_being(being_id_2, 10)) == 1
        ep = store.list_recent_by_being(being_id_2, 10)[0]
        assert "失敗" in ep.outcome
        assert "罠が発動した" in ep.outcome

    def test_llm_api_failure_does_not_persist_episode(self) -> None:
        """LLM API 失敗では execute に至らないためエピソードは増えない。"""
        mapper = ToolCommandMapper(
            handler_map={
                TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(success=True, message="ok")
            }
        )
        orch, store = _orchestrator_with_episode(
            llm_client=StubLlmClient(
                exception_to_raise=LlmApiCallException("timeout", error_code="LLM_API_CALL_FAILED")
            ),
            mapper=mapper,
        )
        orch.run_turn(PlayerId(3))
        assert store.list_recent_by_being(being_id, 10) == []

    def test_no_tool_call_does_not_persist_episode(self) -> None:
        """tool_call 無しでは execute に至らない。"""
        mapper = ToolCommandMapper(
            handler_map={
                TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(success=True, message="ok")
            }
        )
        orch, store = _orchestrator_with_episode(
            llm_client=StubLlmClient(tool_call_to_return=None),
            mapper=mapper,
        )
        orch.run_turn(PlayerId(4))
        assert store.list_recent_by_being(being_id, 10) == []

    def test_subjective_validation_error_does_not_persist_episode(self) -> None:
        """主観入力検証エラーは execute 前に終わるため保存しない。"""
        mapper = ToolCommandMapper(
            handler_map={
                "spot_graph_interact": lambda pid, a: LlmCommandResultDto(success=True, message="ok")
            }
        )
        orch, store = _orchestrator_with_episode(
            llm_client=StubLlmClient(
                tool_call_to_return={"name": "spot_graph_interact", "arguments": {}}
            ),
            mapper=mapper,
        )
        orch.run_turn(PlayerId(5))
        assert store.list_recent_by_being(being_id, 10) == []

    def test_subjective_validation_error_preserves_expected_result_in_action_store(self) -> None:
        """#552 PR-A: validation 失敗でも構造化 expected_result を action_store に残す。

        sanitizer が action_summary の JSON から expected_result を落とすので、失敗
        経路で構造化フィールドにも渡さないと、失敗行の [予測:] が完全に消える。"""
        mapper = ToolCommandMapper(
            handler_map={
                "spot_graph_interact": lambda pid, a: LlmCommandResultDto(success=True, message="ok")
            }
        )
        orch, _ = _orchestrator_with_episode(
            llm_client=StubLlmClient(
                tool_call_to_return={
                    "name": "spot_graph_interact",
                    # inner_thought 欠落で validation 失敗。だが予測は宣言済み。
                    "arguments": {
                        "object_label": "OBJ1",
                        "action_name": "inspect",
                        "expected_result": "祭壇が光る",
                        "intention": "封印を確かめる",
                    },
                }
            ),
            mapper=mapper,
        )
        orch.run_turn(PlayerId(5))
        entries = orch._action_result_store.get_recent(PlayerId(5), 10)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.success is False
        # JSON からは落ちるが構造化フィールドには残る
        assert "expected_result" not in entry.action_summary
        assert entry.expected_result == "祭壇が光る"
        assert entry.intention == "封印を確かめる"

    def test_argument_resolution_error_does_not_persist_episode(self) -> None:
        """引数解決失敗は execute 前に終わるため保存しない。"""
        mapper = ToolCommandMapper(
            handler_map={
                TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(success=True, message="ok")
            }
        )
        orch, store = _orchestrator_with_episode(
            llm_client=StubLlmClient(
                tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}}
            ),
            mapper=mapper,
            resolver=_FailingResolver(),
        )
        orch.run_turn(PlayerId(6))
        assert store.list_recent_by_being(being_id, 10) == []

    def test_episodic_coordinator_none_is_noop(self) -> None:
        """チャンク協調を注入しない場合はエピソードを増やさない（クラッシュもしない）。"""
        mapper = ToolCommandMapper(
            handler_map={
                TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(
                    success=True, message="x", was_no_op=True
                )
            }
        )
        episode_store = InMemorySubjectiveEpisodeStore()
        orch = LlmAgentOrchestrator(
            prompt_builder=_StubPromptBuilder(),
            llm_client=StubLlmClient(
                tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}}
            ),
            tool_command_mapper=mapper,
            action_result_store=DefaultActionResultStore(max_entries_per_player=10),
            episodic_chunk_coordinator=None,
        )
        orch.run_turn(PlayerId(8))
        assert episode_store.list_recent_by_being(being_id, 10) == []
