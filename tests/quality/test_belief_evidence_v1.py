"""Quality-check シナリオ ``belief_evidence_v1``: 学習の素材が観測可能になったか。

U2 (証拠台帳統一設計 §2 U2) の DoD: 「質感シナリオ pytest を 1 本以上」
(LLM を呼ばず prompt / 構造を点検するテスト)。U2 は prompt を一切変えない
(semantic の想起挙動は不変) ため、`tests/quality/test_prediction_v1.py`
(prompt dump) と対称に、**転記された BeliefEvidence + trace payload の構造**
を `docs/quality_checks/belief_evidence_v1.trace.txt` に dump して人が読める
形にする。

ハーネス注:
- 実 LLM は呼ばない。``EpisodicChunkCoordinator`` に chunk 主観補完の
  スタブ port (固定 JSON を返すだけ) を注入し、決定論的に
  prediction_error 付き episode を作る。
- 判断すべきは「evidence の cue_signature / source_kind / text が意味の
  取れる形で残っているか」で、値そのものの妥当性は人が dump を読んで判断
  する (LLM 品質の検証は L2 replay の仕事、本テストのスコープ外)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

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
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)

_DUMP_DIR = Path(__file__).resolve().parents[2] / "docs" / "quality_checks"


class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
    """chunk 主観補完 LLM のスタブ。QUALITY_MARKER 付きの固定文言を返す。"""

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "interpreted": "QUALITY_MARKER_INTERPRETED: 探索は空振りに終わった",
            "recall_text": "QUALITY_MARKER_RECALL: 浜辺を探索したが何も見つからなかった",
            "prediction_error": (
                "QUALITY_MARKER_PREDICTION_ERROR: 何か見つかるはずと期待したが"
                "何も無かった"
            ),
        }


def _capture_trace(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


def _dump_belief_evidence(events: list, evidences: list) -> Path:
    """BELIEF_EVIDENCE trace payload + buffer 内容を人が読める形で書き出す。"""
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DUMP_DIR / "belief_evidence_v1.trace.txt"
    parts: list[str] = []
    parts.append("# belief_evidence_v1\n")
    parts.append(
        "# このファイルは tests/quality/test_belief_evidence_v1.py から\n"
        "# 再生成される。手で編集しないこと。\n\n"
    )
    parts.append("=== BELIEF_EVIDENCE trace events ===\n")
    for i, ev in enumerate(events):
        parts.append(f"--- event[{i}] tick={ev.tick} ---\n")
        for key, value in ev.payload.items():
            parts.append(f"  {key}: {value}\n")
    parts.append("\n=== evidence buffer (list_all_by_being) ===\n")
    for i, evidence in enumerate(evidences):
        parts.append(f"--- evidence[{i}] ---\n")
        parts.append(f"  evidence_id: {evidence.evidence_id}\n")
        parts.append(f"  source_kind: {evidence.source_kind.value}\n")
        parts.append(f"  episode_ids: {evidence.episode_ids}\n")
        parts.append(f"  cue_signature: {evidence.cue_signature}\n")
        parts.append(f"  text: {evidence.text}\n")
        parts.append(f"  salience: {evidence.salience}\n")
        parts.append(f"  tick: {evidence.tick}\n")
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _build_coord(*, transcriber: BeliefEvidenceTranscriber, recorder):
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory()
    action_store = DefaultActionResultStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(being_repo)
    being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
    subjective_service = EpisodicChunkSubjectiveFieldsService(_StubPort())
    coord = EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding,
        action_result_store=action_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
        chunk_subjective_fields_service=subjective_service,
        trace_recorder=recorder,
        current_tick_provider=lambda: 12,
        being_attachment_resolver=resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
        belief_evidence_transcriber=transcriber,
    )
    return coord, buffer, action_store, being_id


def _trigger_chunk_close(coord, buffer, action_store, player_id: PlayerId) -> None:
    t0 = datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc)
    action_store.append(
        player_id,
        action_summary="explore(浜辺)",
        result_summary="何も見つからなかった",
        occurred_at=t0,
        tool_name="explore",
        expected_result="何か見つかるはず",
    )
    coord.after_action_recorded(player_id)
    buffer.append(
        player_id,
        ObservationEntry(
            occurred_at=datetime(2026, 7, 5, 9, 0, 30, tzinfo=timezone.utc),
            output=ObservationOutput(
                prose="砂浜には何もなかった",
                structured={"type": "x"},
                observation_category="environment",
                breaks_movement=True,
            ),
            game_time_label=None,
        ),
    )
    action_store.append(
        player_id,
        action_summary="wait",
        result_summary="時間が過ぎた",
        occurred_at=datetime(2026, 7, 5, 9, 1, tzinfo=timezone.utc),
    )
    coord.after_action_recorded(player_id)
    action_store.append(
        player_id,
        action_summary="move",
        result_summary="移動した",
        occurred_at=datetime(2026, 7, 5, 9, 2, tzinfo=timezone.utc),
        scene_boundary=True,
    )
    coord.after_action_recorded(player_id)


@pytest.mark.quality
class TestBeliefEvidenceV1:
    """chunk 主観補完で prediction_error が確定した瞬間の evidence 転記を
    dump し、構造を人が確認できるようにする。LLM は呼ばない (スタブ port)。"""

    def test_prediction_error_dump(self) -> None:
        """prediction error の転記構造を dump する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 12,
        )
        coord, buffer, action_store, being_id = _build_coord(
            transcriber=transcriber, recorder=recorder
        )

        _trigger_chunk_close(coord, buffer, action_store, PlayerId(1))

        belief_events = [
            e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE
        ]
        evidences = buffer_store.list_all_by_being(being_id)
        dump_path = _dump_belief_evidence(belief_events, evidences)

        # runtime regression 検知のための最小限の sanity assert。
        # 質感の判断 (cue_signature の妥当性・文言の質) は dump を人が読む。
        assert dump_path.exists()
        assert len(evidences) == 1
        evidence = evidences[0]
        assert evidence.source_kind.value == "prediction_error"
        assert evidence.cue_signature.startswith("tool:explore")
        assert "QUALITY_MARKER_PREDICTION_ERROR" in evidence.text
        assert evidence.tick == 12
        assert len(belief_events) == 1
        assert belief_events[0].payload["being_id"] == being_id.value
