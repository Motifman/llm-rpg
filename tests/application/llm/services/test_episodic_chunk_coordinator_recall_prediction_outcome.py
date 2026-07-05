"""EpisodicChunkCoordinator の同期経路での recall buffer 誤差刻み (U9a)。

U9a (予測誤差統一設計 部品5・誤差駆動再解釈): chunk 主観補完で
prediction_error が確定した瞬間、その予測を立てた in-context recall
observation (= prediction_context_id で特定) に誤差文を刻む。同期経路の
転記点は U2 の belief evidence と同じ「chunk 主観補完 LLM が episode を
merge し終えた直後」。非同期経路 (scheduler) の対応テストは
``test_episodic_subjective_completion_schedulers.py`` にある。
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
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
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
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
    """chunk 主観補完 LLM のスタブ。固定の JSON を返すだけ (実 LLM 呼び出しなし)。"""

    def __init__(self, returns: dict[str, Any]) -> None:
        self._returns = returns

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._returns


def _build_coord(
    *,
    returns: dict[str, Any],
    recall_buffer_store=None,
    error_driven_reinterpretation_enabled: bool = False,
):
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory()
    action_store = DefaultActionResultStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(being_repo)
    being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
    port = _StubPort(returns)
    subjective_service = EpisodicChunkSubjectiveFieldsService(port)
    coord = EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding,
        action_result_store=action_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
        chunk_subjective_fields_service=subjective_service,
        being_attachment_resolver=resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
        recall_buffer_store=recall_buffer_store,
        error_driven_reinterpretation_enabled=error_driven_reinterpretation_enabled,
    )
    return coord, buffer, action_store, being_id


def _trigger_chunk_close(
    coord,
    buffer,
    action_store,
    player_id: PlayerId,
    *,
    last_action_prediction_context_id: str | None = None,
) -> None:
    """境界を踏んで chunk を確実に close する (MIN=3 ゲート + scene_boundary)。

    最後の action にだけ ``prediction_context_id`` を乗せられるようにして
    いる (既定は None で従来テストと完全互換)。
    """
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    action_store.append(
        player_id, action_summary="wait1", result_summary="ok", occurred_at=t0
    )
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
        prediction_context_id=last_action_prediction_context_id,
    )
    coord.after_action_recorded(player_id)


def _seed_recall_observation(
    store: InMemoryEpisodicRecallBufferStore, being_id, *, prediction_context_id: str
) -> None:
    store.append_by_being(
        being_id,
        EpisodicRecallObservation(
            recall_id="r-1",
            player_id=1,
            episode_id="ep-source",
            recalled_at=datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc),
            source_axes=("temporal",),
            current_state_snapshot="state",
            recent_events_snapshot="events",
            persona_snapshot="persona",
            situation_cues=("cue",),
            turn_index=1,
            prediction_context_id=prediction_context_id,
        ),
    )


class TestEpisodicChunkCoordinatorRecallPredictionOutcomeSyncPath:
    """同期 LLM 補完経路 (chunk_subjective_fields_service 注入時) の刻み。"""

    def test_flag_ON_で_prediction_error_ありなら_recall_observation_に誤差が刻まれる(
        self,
    ) -> None:
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        coord, buffer, action_store, being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            },
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
        )
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")

        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_prediction_context_id="pc-1",
        )

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error == "何も見つからなかった"

    def test_prediction_error_なしなら誤差は刻まれない(self) -> None:
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        coord, buffer, action_store, being_id = _build_coord(
            returns={"interpreted": "I", "recall_text": "R"},
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
        )
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")

        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_prediction_context_id="pc-1",
        )

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error is None

    def test_flag_OFF_既定なら_prediction_error_ありでも刻まれない(self) -> None:
        """error_driven_reinterpretation_enabled=False (既定) は導入前と一致。"""
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        coord, buffer, action_store, being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            },
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=False,
        )
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")

        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_prediction_context_id="pc-1",
        )

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error is None

    def test_recall_buffer_store_未配線なら例外を投げず完了する(self) -> None:
        """recall_buffer_store=None (既定) は既存動作と完全互換。"""
        coord, buffer, action_store, _being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "外れた",
            },
            recall_buffer_store=None,
            error_driven_reinterpretation_enabled=True,
        )
        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_prediction_context_id="pc-1",
        )
