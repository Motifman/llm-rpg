"""Quality-check シナリオ ``belief_attribution_v1``: attribution + CONFIRMATION の
固着パス入出力構造 (U4)。

U4 (予測誤差統一設計 部品3) の DoD: 「質感シナリオ pytest を 1 本以上」
(LLM を呼ばず prompt / 構造を点検するテスト)。S3 (学びの訂正) 相当の状況 —
「拠点に資源はない」を信じて行動したら資源が見つかった (CONFIRMATION の逆、
つまり反証) と、素直な的中 (CONFIRMATION) の両方を 1 batch に混ぜ、
``BeliefConsolidationCoordinator`` が組み立てる messages と shortlist の
強制搭載結果を ``docs/quality_checks/belief_attribution_v1.trace.txt`` に
dump する。

ハーネス注:
- 実 LLM は呼ばない。``_StubBeliefConsolidationPort`` が固定 decisions JSON
  を返すだけ。
- 判断すべきは「in_context_belief_ids が evidence に載り、cue スコアが
  0 でも shortlist に強制搭載されているか」「CONFIRMATION の evidence が
  正しい source_kind / text で prompt に出ているか」。LLM 品質そのものの
  検証は L2 replay の仕事 (本テストのスコープ外)。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
)
from ai_rpg_world.application.llm.services.belief_confidence import (
    compute_belief_confidence,
)
from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
    BeliefConsolidationCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)

_DUMP_DIR = Path(__file__).resolve().parents[2] / "docs" / "quality_checks"

_BELIEF_ID = "sem-no-resources"


class _StubBeliefConsolidationPort(IBeliefConsolidationCompletionPort):
    """固着パス LLM のスタブ。固定 decisions JSON を返すだけ。"""

    def __init__(self) -> None:
        self.received_messages: list[list[dict[str, Any]]] = []

    def complete_belief_consolidation_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.received_messages.append(messages)
        return {
            "decisions": [
                {
                    "action": "contradict",
                    "belief_id": _BELIEF_ID,
                    "evidence_ids": ["e-error"],
                },
                {
                    "action": "strengthen",
                    "belief_id": _BELIEF_ID,
                    "evidence_ids": ["e-confirm"],
                },
            ]
        }


def _dump_belief_attribution(
    messages: list[dict[str, Any]],
    events: list,
    entries: list[SemanticMemoryEntry],
) -> Path:
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DUMP_DIR / "belief_attribution_v1.trace.txt"
    parts: list[str] = []
    parts.append("# belief_attribution_v1\n")
    parts.append(
        "# このファイルは tests/quality/test_belief_attribution_v1.py から\n"
        "# 再生成される。手で編集しないこと。\n\n"
    )
    parts.append("=== LLM に渡した messages ===\n")
    for i, m in enumerate(messages):
        parts.append(f"--- messages[{i}] role={m['role']} ---\n")
        parts.append(m["content"] + "\n")
    parts.append("\n=== BELIEF_CONSOLIDATION trace events ===\n")
    for i, ev in enumerate(events):
        parts.append(f"--- event[{i}] tick={ev.tick} ---\n")
        for key, value in ev.payload.items():
            parts.append(f"  {key}: {value}\n")
    parts.append("\n=== belief journal (list_for_being) ===\n")
    for i, entry in enumerate(entries):
        parts.append(f"--- entry[{i}] ---\n")
        parts.append(f"  entry_id: {entry.entry_id}\n")
        parts.append(f"  belief_id: {entry.belief_id}\n")
        parts.append(f"  status: {entry.status}\n")
        parts.append(f"  text: {entry.text}\n")
        parts.append(f"  confidence: {entry.confidence}\n")
        parts.append(f"  support_evidence_ids: {entry.support_evidence_ids}\n")
        parts.append(f"  contradict_evidence_ids: {entry.contradict_evidence_ids}\n")
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _capture_trace(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


@pytest.mark.quality
class TestBeliefAttributionV1:
    """S3 (学びの訂正) + CONFIRMATION (的中の支持) を 1 batch に混ぜ、
    in_context_belief_ids による shortlist 強制搭載と prompt 構造を dump する。
    LLM は呼ばない (スタブ port)。"""

    def test_in_context_belief_が_cueスコア0でも強制搭載され_CONFIRMATIONも同居する(
        self,
    ) -> None:
        being_repo = InMemoryBeingRepository()
        resolver = BeingAttachmentResolver(being_repo)
        being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
        evidence_buffer = InMemoryBeliefEvidenceBufferStore()
        semantic_store = InMemorySemanticMemoryStore()
        # 「拠点に資源はない」という既存 belief。tags は cue と無関係
        # (= cue スコアだけでは shortlist に載らない) ことをわざと作る。
        existing = SemanticMemoryEntry(
            entry_id=_BELIEF_ID,
            player_id=1,
            text="拠点に資源はない",
            evidence_episode_ids=("ep-0",),
            confidence=compute_belief_confidence(2, 0),
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            tags=("拠点",),
            belief_id=_BELIEF_ID,
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            support_evidence_ids=("old-e1", "old-e2"),
        )
        semantic_store.add_by_being(being_id, existing)

        # evidence 1: 信じて行動したら外れた (PREDICTION_ERROR + attribution 添付)。
        evidence_buffer.append_by_being(
            being_id,
            BeliefEvidence(
                evidence_id="e-error",
                source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
                episode_ids=("ep-1",),
                cue_signature="tool:search|spot:洞窟",
                text="拠点で資源を探したが、実は見つかった",
                salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                occurred_at=datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc),
                in_context_belief_ids=(_BELIEF_ID,),
            ),
        )
        # evidence 2: 別ターンで同じ belief を信じて行動し、今度は当たった
        # (CONFIRMATION)。
        evidence_buffer.append_by_being(
            being_id,
            BeliefEvidence(
                evidence_id="e-confirm",
                source_kind=BeliefEvidenceSourceKind.CONFIRMATION,
                episode_ids=("ep-2",),
                cue_signature="tool:search|spot:洞窟",
                text="予測が当たった: 拠点には何もないはず",
                salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                occurred_at=datetime(2026, 7, 5, 9, 5, tzinfo=timezone.utc),
                in_context_belief_ids=(_BELIEF_ID,),
            ),
        )

        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        port = _StubBeliefConsolidationPort()
        coordinator = BeliefConsolidationCoordinator(
            evidence_buffer_store=evidence_buffer,
            semantic_store=semantic_store,
            completion=port,
            being_attachment_resolver=resolver,
            default_world_id=DEFAULT_SINGLE_WORLD_ID,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 40,
            # U4: attribution ON でこそ CONFIRMATION 節が prompt に出る。
            belief_attribution_enabled=True,
        )

        processed = coordinator.flush_player(PlayerId(1))

        entries = semantic_store.list_for_being(being_id)
        events = [
            e for e in captured if e.kind == TraceEventKind.BELIEF_CONSOLIDATION
        ]
        dump_path = _dump_belief_attribution(
            port.received_messages[0], events, entries
        )

        # runtime regression 検知のための最小限の sanity assert。
        # 質感の判断 (プロンプト文言・強制搭載の妥当性) は dump を人が読む。
        assert dump_path.exists()
        assert processed == 2
        assert evidence_buffer.list_all_by_being(being_id) == []
        # shortlist に cue スコア無関係でも belief_id が強制搭載されている。
        assert events[0].payload["shortlist_belief_ids"] == [_BELIEF_ID]
        # prompt の evidence payload に CONFIRMATION の source_kind が載る。
        user_message = port.received_messages[0][1]["content"]
        payload = json.loads(
            user_message.split("\n", 1)[1] if "\n" in user_message else user_message
        )
        source_kinds = {e["source_kind"] for e in payload["evidence"]}
        assert source_kinds == {"prediction_error", "confirmation"}
        # system prompt に CONFIRMATION の意味づけが追記されている。
        system_message = port.received_messages[0][0]["content"]
        assert "confirmation" in system_message
        # decisions 適用結果: contradict + strengthen が両方効いている
        # (confidence は support=3 (old-e1,old-e2,e-confirm), contradict=1 (e-error))。
        target = next(e for e in entries if e.belief_id == _BELIEF_ID)
        assert "e-error" in target.contradict_evidence_ids
        assert "e-confirm" in target.support_evidence_ids
