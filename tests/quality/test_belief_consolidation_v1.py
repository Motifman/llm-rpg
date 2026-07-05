"""Quality-check シナリオ ``belief_consolidation_v1``: 固着パスの入出力構造。

U3b (固着パス本体) の DoD: 「質感シナリオ pytest を 1 本以上」(LLM を呼ばず
prompt / 構造を点検するテスト)。``BeliefConsolidationCoordinator`` が
組み立てる messages (system prompt + evidence/shortlist payload) と、stub
completion が返した decisions を belief journal へ適用した結果を
``docs/quality_checks/belief_consolidation_v1.trace.txt`` に dump する。

ハーネス注:
- 実 LLM は呼ばない。``_StubBeliefConsolidationPort`` が固定 decisions JSON
  を返すだけ。
- 判断すべきは「evidence / shortlist が意味の取れる形で prompt に載って
  いるか」「decisions が journal に正しく反映されているか」で、LLM 品質
  そのものの検証は L2 replay の仕事 (本テストのスコープ外)。
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
                    "action": "create",
                    "text": "この島の探索は空振りが多い",
                    "importance": 6,
                    "tags": ["探索", "浜辺"],
                    "evidence_ids": ["e1", "e2", "e3"],
                }
            ]
        }


def _evidence(evidence_id: str, i: int) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
        episode_ids=(f"ep-{i}",),
        cue_signature="tool:explore|spot:浜辺",
        text=f"探索したが何も見つからなかった ({i} 回目)",
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=datetime(2026, 7, 5, 9, i, tzinfo=timezone.utc),
    )


def _dump_belief_consolidation(
    messages: list[dict[str, Any]],
    events: list,
    entries: list[SemanticMemoryEntry],
) -> Path:
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DUMP_DIR / "belief_consolidation_v1.trace.txt"
    parts: list[str] = []
    parts.append("# belief_consolidation_v1\n")
    parts.append(
        "# このファイルは tests/quality/test_belief_consolidation_v1.py から\n"
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
class TestBeliefConsolidationV1:
    """S1 (反復誤差の一般化) 相当の evidence 3 件を 1 回の flush で処理し、
    prompt 構造 + journal 反映を dump する。LLM は呼ばない (スタブ port)。"""

    def test_同型evidence3件が1件のcreateに畳まれる様子を_dump_する(self) -> None:
        being_repo = InMemoryBeingRepository()
        resolver = BeingAttachmentResolver(being_repo)
        being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
        evidence_buffer = InMemoryBeliefEvidenceBufferStore()
        semantic_store = InMemorySemanticMemoryStore()
        # shortlist に載る既存 belief を 1 件仕込む (関連 tag 一致)。
        existing = SemanticMemoryEntry(
            entry_id="sem-existing",
            player_id=1,
            text="この島は資源が乏しい",
            evidence_episode_ids=("ep-0",),
            confidence=compute_belief_confidence(1, 0),
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            tags=("explore",),
            belief_id="sem-existing",
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            support_evidence_ids=("old-e",),
        )
        semantic_store.add_by_being(being_id, existing)
        for i in range(3):
            evidence_buffer.append_by_being(being_id, _evidence(f"e{i+1}", i))

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
            current_tick_provider=lambda: 30,
        )

        processed = coordinator.flush_player(PlayerId(1))

        entries = semantic_store.list_for_being(being_id)
        events = [
            e for e in captured if e.kind == TraceEventKind.BELIEF_CONSOLIDATION
        ]
        dump_path = _dump_belief_consolidation(
            port.received_messages[0], events, entries
        )

        # runtime regression 検知のための最小限の sanity assert。
        # 質感の判断 (プロンプト文言・畳み込みの妥当性) は dump を人が読む。
        assert dump_path.exists()
        assert processed == 3
        assert evidence_buffer.list_all_by_being(being_id) == []
        created = [e for e in entries if e.entry_id != "sem-existing"]
        assert len(created) == 1
        assert created[0].text == "この島の探索は空振りが多い"
        assert set(created[0].support_evidence_ids) == {"e1", "e2", "e3"}
        assert len(events) == 1
        assert events[0].payload["being_id"] == being_id.value
        assert "sem-existing" in events[0].payload["shortlist_belief_ids"]
        # system prompt に固着パスの絶対ルール (畳み込み方針) が載っていること。
        system_message = port.received_messages[0][0]["content"]
        assert "畳" in system_message
        user_message = port.received_messages[0][1]["content"]
        payload = json.loads(
            user_message.split("\n", 1)[1] if "\n" in user_message else user_message
        )
        assert len(payload["evidence"]) == 3
        assert len(payload["shortlist"]) == 1
