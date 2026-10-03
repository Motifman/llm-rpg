"""EpisodicChunkCoordinator が、確定して外れた予期を次に閉じる chunk の主観補完へ渡し、chunk の prediction_error を信念の材料にしない挙動を保証する (#1443)。

同期経路 (``chunk_subjective_fields_service`` 注入時) で、``after_action_recorded``
が chunk を close するまで実際に action / observation を流し込む。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tests.memory_turn_helpers import ZERO_TURN

from ai_rpg_world.application.being.being_attachment_resolver import BeingAttachmentResolver
from ai_rpg_world.application.being.being_provisioning_service import BeingProvisioningService
from ai_rpg_world.application.llm.contracts.chunk_encoding import SettledMissedExpectation
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.belief_evidence_transcriber import BeliefEvidenceTranscriber
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import EpisodicChunkCoordinator
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import EpisodicChunkSubjectiveFieldsService
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.services.observation_context_buffer import DefaultObservationContextBuffer
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import Likelihood
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import InMemoryBeingRepository


class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
    """chunk 主観補完 LLM のスタブ。固定の JSON を返すだけ (実 LLM 呼び出しなし)。"""

    def __init__(self, returns: dict[str, Any]) -> None:
        self._returns = returns

    def complete_episode_subjective_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return self._returns

def _build_coord(*, returns: dict[str, Any], belief_evidence_transcriber=None):
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory()
    action_store = DefaultActionResultStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(being_repo)
    being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
    port = _StubPort(returns)
    subjective_service = EpisodicChunkSubjectiveFieldsService(port)
    coord = EpisodicChunkCoordinator(observation_buffer=buffer, short_term_memory=sliding, action_result_store=action_store, episodic_episode_store=episode_store, chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(), chunk_subjective_fields_service=subjective_service, belief_evidence_transcriber=belief_evidence_transcriber)
    return (coord, buffer, action_store, being_id)

def _trigger_chunk_close(coord, buffer, action_store, player_id: PlayerId, being_id, *, start_hour: int=12) -> None:
    """境界を踏んで chunk を確実に close する (MIN=3 ゲート + scene_boundary)。"""
    action_store.append(player_id, action_summary='wait1', result_summary='ok', occurred_at=datetime(2026, 5, 1, start_hour, 0, tzinfo=timezone.utc))
    coord.after_action_recorded(player_id, being_id)
    buffer.append(player_id, ObservationEntry(occurred_at=datetime(2026, 5, 1, start_hour, 0, 30, tzinfo=timezone.utc), output=ObservationOutput(prose='salient event', structured={'type': 'x'}, observation_category='social', breaks_movement=True), game_time_label=None))
    action_store.append(player_id, action_summary='wait2', result_summary='ok', occurred_at=datetime(2026, 5, 1, start_hour, 1, tzinfo=timezone.utc))
    coord.after_action_recorded(player_id, being_id)
    action_store.append(player_id, action_summary='move', result_summary='ok', occurred_at=datetime(2026, 5, 1, start_hour, 2, tzinfo=timezone.utc), scene_boundary=True)
    coord.after_action_recorded(player_id, being_id)

def _missed(event_id: str='exp-1@5') -> SettledMissedExpectation:
    return SettledMissedExpectation(event_id=event_id, content='潮が引いて干潟に下りられる', likelihood=Likelihood.PROBABLY)


class TestChunkPredictionErrorIsNotBeliefMaterial:
    """chunk の prediction_error は、確定した予期と二重に数えないよう信念の材料にしない挙動を保証する。"""

    def test_prediction_error_of_chunk_adds_no_evidence(self) -> None:
        """外れた予期について LLM が prediction_error を書いても、chunk の完了点では証拠を積まない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        (coord, buffer, action_store, being_id) = _build_coord(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': '潮が満ちていて下りられなかった'}, belief_evidence_transcriber=transcriber)
        coord.note_settled_miss(being_id, _missed())
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id)
        assert buffer_store.list_all_by_being(being_id) == []


class TestSettledMissReachesNextChunk:
    """外れたで確定した予期が、次に閉じる chunk の主観補完に 1 回だけ渡る挙動を保証する。"""

    def test_noted_miss_lets_chunk_keep_llm_prediction_error(self) -> None:
        """chunk を閉じる前に外れの確定を受け取っていれば、その chunk の prediction_error に LLM の文が残る。"""
        (coord, buffer, action_store, being_id) = _build_coord(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': '潮が満ちていて下りられなかった'})
        coord.note_settled_miss(being_id, _missed())
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id)
        (episode,) = coord._episodic_episode_store.list_all_by_being(being_id)
        assert episode.prediction_error == '潮が満ちていて下りられなかった'

    def test_without_noted_miss_chunk_prediction_error_is_none(self) -> None:
        """外れの確定を受け取っていない chunk では、LLM が書いても prediction_error は None になる。"""
        (coord, buffer, action_store, being_id) = _build_coord(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': '潮が満ちていて下りられなかった'})
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id)
        (episode,) = coord._episodic_episode_store.list_all_by_being(being_id)
        assert episode.prediction_error is None

    def test_noted_miss_is_used_by_one_chunk_only(self) -> None:
        """一度 chunk に渡した外れは、その次の chunk には渡らない。"""
        (coord, buffer, action_store, being_id) = _build_coord(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': 'ずれ'})
        coord.note_settled_miss(being_id, _missed())
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id)
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id, start_hour=13)
        errors = sorted((e.occurred_at, e.prediction_error) for e in coord._episodic_episode_store.list_all_by_being(being_id))
        assert [err for _, err in errors] == ['ずれ', None]

    def test_same_event_noted_twice_is_kept_once(self) -> None:
        """同じ出来事の ID を二度受け取っても 1 件として持ち、False を返す。一度 chunk に渡したあとでも同じ。"""
        (coord, buffer, action_store, being_id) = _build_coord(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': 'ずれ'})
        assert coord.note_settled_miss(being_id, _missed()) is True
        assert coord.note_settled_miss(being_id, _missed()) is False
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id)
        assert coord.note_settled_miss(being_id, _missed()) is False
        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1), being_id, start_hour=13)
        errors = sorted((e.occurred_at, e.prediction_error) for e in coord._episodic_episode_store.list_all_by_being(being_id))
        assert [err for _, err in errors] == ['ずれ', None]
