"""EpisodicChunkCoordinator の同期経路での pending prediction 清算 (U10b)。

U10b (予測誤差統一設計 部品6・清算): store に窓の開いた約束があると、chunk
補完プロンプトに【保留中の約束】節が載り、chunk 補完 LLM が返した
``pending_resolutions`` が完了点で清算される (evidence 転記 + store から除去)。
tick_to を過ぎた未決着の約束は黙って失効する。flag OFF なら約束が store に
あってもプロンプトに載らず清算もされない。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    BeliefEvidenceTranscriber,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
    InMemoryPendingPredictionStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
    def __init__(self, returns: dict[str, Any]) -> None:
        self._returns = returns
        self.last_messages: list[dict[str, Any]] | None = None

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.last_messages = list(messages)
        return self._returns


def _build_coord(*, returns, pending_prediction_enabled, current_tick):
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory()
    action_store = DefaultActionResultStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(being_repo)
    being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
    pending_store = InMemoryPendingPredictionStore()
    buffer_store = InMemoryBeliefEvidenceBufferStore()
    transcriber = BeliefEvidenceTranscriber(buffer_store)
    port = _StubPort(returns)
    subjective_service = EpisodicChunkSubjectiveFieldsService(
        port, pending_prediction_enabled=pending_prediction_enabled
    )
    coord = EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding,
        action_result_store=action_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
        chunk_subjective_fields_service=subjective_service,
        being_attachment_resolver=resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
        belief_evidence_transcriber=transcriber,
        pending_prediction_store=pending_store,
        pending_prediction_enabled=pending_prediction_enabled,
        current_tick_provider=(lambda: current_tick),
    )
    return coord, buffer, action_store, being_id, pending_store, buffer_store, port


def _pending(pending_id, *, tick_from, tick_to) -> PendingPrediction:
    return PendingPrediction(
        pending_id=pending_id,
        text=f"約束-{pending_id}",
        resolution_cues=("player:カイト",),
        tick_from=tick_from,
        tick_to=tick_to,
        origin_episode_id="ep-origin",
        created_tick=tick_from,
    )


def _trigger_chunk_close(coord, buffer, action_store, player_id: PlayerId) -> None:
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    action_store.append(player_id, action_summary="wait1", result_summary="ok", occurred_at=t0)
    coord.after_action_recorded(player_id)
    buffer.append(
        player_id,
        ObservationEntry(
            occurred_at=datetime(2026, 5, 1, 12, 0, 30, tzinfo=timezone.utc),
            output=ObservationOutput(
                prose="salient event",
                structured={"type": "x"},
                observation_category="social",
                breaks_movement=True,
            ),
            game_time_label=None,
        ),
    )
    action_store.append(
        player_id,
        action_summary="wait2",
        result_summary="ok",
        occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc),
    )
    coord.after_action_recorded(player_id)
    action_store.append(
        player_id,
        action_summary="move",
        result_summary="ok",
        occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc),
        scene_boundary=True,
    )
    coord.after_action_recorded(player_id)


class TestCoordinatorPendingResolutionSyncPath:
    def test_broken_verdict_transcribes_and_removes_pending(self) -> None:
        coord, buffer, action_store, being_id, pending_store, buffer_store, port = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "pending_resolutions": [{"pending_id": "p1", "verdict": "broken"}],
            },
            pending_prediction_enabled=True,
            current_tick=15,
        )
        pending_store.add_by_being(being_id, _pending("p1", tick_from=10, tick_to=20))

        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))

        # 約束はプロンプトに載った
        user_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "user"), ""
        )
        assert "[p1]" in user_content
        # 清算された
        assert pending_store.list_all_by_being(being_id) == []
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind is BeliefEvidenceSourceKind.PENDING_RESOLUTION
        assert rows[0].salience == "high"

    def test_expired_pending_removed_without_verdict(self) -> None:
        coord, buffer, action_store, being_id, pending_store, buffer_store, port = _build_coord(
            returns={"interpreted": "I", "recall_text": "R"},
            pending_prediction_enabled=True,
            current_tick=99,
        )
        pending_store.add_by_being(being_id, _pending("old", tick_from=1, tick_to=5))

        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))

        assert pending_store.list_all_by_being(being_id) == []
        assert buffer_store.list_all_by_being(being_id) == []

    def test_flag_off_keeps_pending_and_omits_prompt_section(self) -> None:
        coord, buffer, action_store, being_id, pending_store, buffer_store, port = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "pending_resolutions": [{"pending_id": "p1", "verdict": "broken"}],
            },
            pending_prediction_enabled=False,
            current_tick=15,
        )
        pending_store.add_by_being(being_id, _pending("p1", tick_from=10, tick_to=20))

        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))

        user_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "user"), ""
        )
        assert "保留中の約束" not in user_content
        # 清算も失効もしない (約束は残る)
        assert len(pending_store.list_all_by_being(being_id)) == 1
        assert buffer_store.list_all_by_being(being_id) == []
