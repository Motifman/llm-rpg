"""EpisodicChunkCoordinator の同期経路での BeliefEvidence 転記 (U2)。

U2 (証拠台帳統一設計 §2 U2): 同期経路 (``chunk_subjective_fields_service``
注入時) の転記点は「chunk 主観補完 LLM が episode を merge し終えた直後」。
本テストは ``after_action_recorded`` が chunk を close するまで実際に
action / observation を流し込み、生成された episode の
``prediction_error`` が非 None のとき evidence が 1 件積まれることを
保証する。非同期経路 (scheduler) の対応テストは
``test_episodic_subjective_completion_schedulers.py`` にある。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
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
    belief_evidence_transcriber=None,
    belief_attribution_enabled: bool = False,
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
        belief_evidence_transcriber=belief_evidence_transcriber,
        belief_attribution_enabled=belief_attribution_enabled,
    )
    return coord, buffer, action_store, being_id


def _trigger_chunk_close(
    coord,
    buffer,
    action_store,
    player_id: PlayerId,
    *,
    last_action_in_context_belief_ids: tuple[str, ...] = (),
    last_action_expected_result: str | None = None,
) -> None:
    """境界を踏んで chunk を確実に close する (MIN=3 ゲート + scene_boundary)。

    U4 のテスト用に、chunk 内最後の action へ ``in_context_belief_ids`` /
    ``expected_result`` を乗せられるようにしている (既定は空/None で
    従来テストと完全互換)。
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
        in_context_belief_ids=last_action_in_context_belief_ids,
        expected_result=last_action_expected_result,
    )
    coord.after_action_recorded(player_id)


class TestEpisodicChunkCoordinatorBeliefEvidenceSyncPath:
    """同期 LLM 補完経路 (chunk_subjective_fields_service 注入時) の転記。"""

    def test_prediction_error_ありなら_evidence_が_1件積まれる(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        coord, buffer, action_store, being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            },
            belief_evidence_transcriber=transcriber,
        )
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].text == "何も見つからなかった"

    def test_prediction_error_なしなら_evidence_は_積まれない(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        coord, buffer, action_store, being_id = _build_coord(
            returns={"interpreted": "I", "recall_text": "R"},
            belief_evidence_transcriber=transcriber,
        )
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))

        assert buffer_store.list_all_by_being(being_id) == []

    def test_transcriber_未注入_flag_OFF_相当なら_何も積まない(self) -> None:
        """belief_evidence_transcriber=None (既定) は既存動作と完全互換。"""
        coord, buffer, action_store, being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "外れた",
            },
            belief_evidence_transcriber=None,
        )
        # 例外を投げず従来通り完了することだけを確認する (evidence 用の
        # store をそもそも持たないので、成功していれば OK)。
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))


class TestEpisodicChunkCoordinatorBeliefAttributionSyncPath:
    """U4 (予測誤差統一設計 部品3): 同期経路での attribution + CONFIRMATION。"""

    def test_belief_attribution_enabled_で_prediction_error_evidence_に_in_context_belief_ids_が添付される(
        self,
    ) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        coord, buffer, action_store, being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            },
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=True,
        )
        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_in_context_belief_ids=("sem-1",),
            last_action_expected_result="何か見つかるはず",
        )

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].in_context_belief_ids == ("sem-1",)

    def test_belief_attribution_enabled_で_prediction_error_None_かつ_in_context_belief_あり_かつ_expected_result_ありなら_CONFIRMATION(
        self,
    ) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        coord, buffer, action_store, being_id = _build_coord(
            returns={"interpreted": "I", "recall_text": "R"},
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=True,
        )
        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_in_context_belief_ids=("sem-1",),
            last_action_expected_result="何か見つかるはず",
        )

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind.value == "confirmation"
        assert rows[0].in_context_belief_ids == ("sem-1",)

    def test_belief_attribution_enabled_が_False_既定なら_in_context_belief_ids_を計算せず添付しない(
        self,
    ) -> None:
        """flag OFF (既定) では chunk_coordinator が attribution 自体を計算
        しないため、action に in_context_belief_ids が乗っていても evidence
        には添付されない (= U4 導入前と一致)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        coord, buffer, action_store, being_id = _build_coord(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            },
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=False,
        )
        _trigger_chunk_close(
            coord,
            buffer,
            action_store,
            PlayerId(1),
            last_action_in_context_belief_ids=("sem-1",),
            last_action_expected_result="何か見つかるはず",
        )

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].in_context_belief_ids == ()
