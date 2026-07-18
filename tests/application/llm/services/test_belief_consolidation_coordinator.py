"""固着パス BeliefConsolidationCoordinator の検証 (U3b)。

LLM は stub (``_FakeBeliefConsolidationPort``) を使い、実際の litellm 呼び出し
は一切行わない。
"""

from __future__ import annotations

import json
import logging

import pytest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
)
from ai_rpg_world.application.llm.services.belief_confidence import (
    compute_belief_confidence,
)
from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
    BeliefConsolidationCoordinator,
    DEFAULT_CUE_SIGNATURE_REPEAT_THRESHOLD,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_stagnation_pressure_store import (
    InMemoryStagnationPressureStore,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SEMANTIC_MEMORY_STATUS_INACTIVE,
    SEMANTIC_MEMORY_STATUS_SUPERSEDED,
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)

_WORLD_ID = WorldId(1)
_UNSET = object()


class _FakeBeliefConsolidationPort(IBeliefConsolidationCompletionPort):
    def __init__(self, outcome: dict[str, Any] | BaseException) -> None:
        self.outcome = outcome
        self.calls: list[list[dict[str, Any]]] = []

    def complete_belief_consolidation_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.calls.append(messages)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@dataclass
class _Setup:
    coordinator: BeliefConsolidationCoordinator
    evidence_buffer: InMemoryBeliefEvidenceBufferStore
    semantic_store: InMemorySemanticMemoryStore
    port: _FakeBeliefConsolidationPort
    being_id: BeingId
    player_id: PlayerId
    stagnation_pressure_store: InMemoryStagnationPressureStore


def _build_setup(
    *,
    outcome: dict[str, Any] | BaseException,
    turn_interval: int = 10,
    batch_size: int = 8,
    shortlist_top_k: int = 5,
    cue_signature_repeat_threshold: int = DEFAULT_CUE_SIGNATURE_REPEAT_THRESHOLD,
    contradict_inactive_threshold: float = 0.2,
    high_salience_batch_cap: int = 3,
    completion: Any = _UNSET,
    belief_attribution_enabled: bool = False,
    goal_reflect_enabled: bool = False,
    hearsay_enabled: bool = False,
    objective_text_provider: Any = None,
    reflect_observation_sink: Any = None,
    stall_min_interval_turns: int = 15,
    trace_recorder_provider: Any = None,
    goal_stagnation_evidence_enabled: bool = False,
    stagnation_pressure_enabled: bool = False,
    stagnation_pressure_store: Any = _UNSET,
) -> _Setup:
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    player_id = PlayerId(7)
    being_id = provisioning.ensure_attached(player_id)

    evidence_buffer = InMemoryBeliefEvidenceBufferStore()
    semantic_store = InMemorySemanticMemoryStore()
    resolved_stagnation_store = (
        InMemoryStagnationPressureStore()
        if stagnation_pressure_store is _UNSET
        else stagnation_pressure_store
    )
    port = _FakeBeliefConsolidationPort(outcome)
    coordinator = BeliefConsolidationCoordinator(
        evidence_buffer_store=evidence_buffer,
        semantic_store=semantic_store,
        completion=port if completion is _UNSET else completion,
        turn_interval=turn_interval,
        batch_size=batch_size,
        shortlist_top_k=shortlist_top_k,
        cue_signature_repeat_threshold=cue_signature_repeat_threshold,
        contradict_inactive_threshold=contradict_inactive_threshold,
        high_salience_batch_cap=high_salience_batch_cap,
        being_attachment_resolver=resolver,
        default_world_id=_WORLD_ID,
        belief_attribution_enabled=belief_attribution_enabled,
        goal_reflect_enabled=goal_reflect_enabled,
        hearsay_enabled=hearsay_enabled,
        objective_text_provider=objective_text_provider,
        reflect_observation_sink=reflect_observation_sink,
        stall_min_interval_turns=stall_min_interval_turns,
        trace_recorder_provider=trace_recorder_provider,
        goal_stagnation_evidence_enabled=goal_stagnation_evidence_enabled,
        stagnation_pressure_enabled=stagnation_pressure_enabled,
        stagnation_pressure_store=resolved_stagnation_store,
    )
    return _Setup(
        coordinator=coordinator,
        evidence_buffer=evidence_buffer,
        semantic_store=semantic_store,
        port=port,
        being_id=being_id,
        player_id=player_id,
        stagnation_pressure_store=resolved_stagnation_store,
    )


def _evidence(
    evidence_id: str,
    *,
    cue_signature: str = "tool:explore",
    text: str = "探索したが何もなかった",
    salience: str = BELIEF_EVIDENCE_SALIENCE_LOW,
    occurred_at: datetime | None = None,
    episode_ids: tuple[str, ...] = ("ep-1",),
    source_kind: BeliefEvidenceSourceKind = BeliefEvidenceSourceKind.PREDICTION_ERROR,
    in_context_belief_ids: tuple[str, ...] = (),
    source_speaker: str | None = None,
) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=source_kind,
        episode_ids=episode_ids,
        cue_signature=cue_signature,
        text=text,
        in_context_belief_ids=in_context_belief_ids,
        salience=salience,
        occurred_at=occurred_at or datetime(2026, 7, 1, tzinfo=timezone.utc),
        source_speaker=source_speaker,
    )


def _belief_entry(
    *,
    entry_id: str = "sem-existing",
    belief_id: str | None = None,
    text: str = "この島の探索は空振りが多い",
    tags: tuple[str, ...] = ("explore",),
    support: tuple[str, ...] = (),
    contradict: tuple[str, ...] = (),
    confirmation_support_count: int = 0,
    hearsay_support_count: int = 0,
    status: str = SEMANTIC_MEMORY_STATUS_ACTIVE,
    created_at: datetime | None = None,
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=7,
        text=text,
        evidence_episode_ids=("ep-0",),
        confidence=compute_belief_confidence(
            len(support), len(contradict),
            confirmation_support_count, hearsay_support_count,
        ),
        created_at=created_at or datetime(2026, 6, 1, tzinfo=timezone.utc),
        tags=tags,
        belief_id=belief_id or entry_id,
        status=status,
        support_evidence_ids=support,
        contradict_evidence_ids=contradict,
        confirmation_support_count=confirmation_support_count,
        hearsay_support_count=hearsay_support_count,
    )


class TestAfterTurnCompletedTriggers:
    """flush 発火条件 (interval / cue_signature 反復 / salience=high) を検証する。"""

    def test_does_not_flush_before_interval(self) -> None:
        """interval 未到達かつ早期トリガーも無ければ LLM を呼ばない。"""
        setup = _build_setup(outcome={"decisions": []}, turn_interval=10)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        for _ in range(9):
            setup.coordinator.after_turn_completed(setup.player_id)

        assert setup.port.calls == []
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1

    def test_flushes_on_tenth_turn(self) -> None:
        """10 ターン目で LLM を呼び、batch が buffer から drain される。"""
        setup = _build_setup(outcome={"decisions": []}, turn_interval=10)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        for _ in range(10):
            setup.coordinator.after_turn_completed(setup.player_id)

        assert len(setup.port.calls) == 1
        assert setup.evidence_buffer.list_all_by_being(setup.being_id) == []

    def test_flushes_early_when_cue_signature_repeats_k_times(self) -> None:
        """同一 cue_signature の evidence が閾値件数に達すると interval を待たず flush する。"""
        setup = _build_setup(
            outcome={"decisions": []},
            turn_interval=10,
            cue_signature_repeat_threshold=3,
        )
        for i in range(3):
            setup.evidence_buffer.append_by_being(
                setup.being_id, _evidence(f"e{i}", cue_signature="tool:explore")
            )

        setup.coordinator.after_turn_completed(setup.player_id)

        assert len(setup.port.calls) == 1

    def test_flushes_early_when_salience_high_present(self) -> None:
        """salience=high の evidence が 1 件でもあれば件数閾値なしで flush する (一撃学習)。"""
        setup = _build_setup(outcome={"decisions": []}, turn_interval=10)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence("e-high", salience=BELIEF_EVIDENCE_SALIENCE_HIGH),
        )

        setup.coordinator.after_turn_completed(setup.player_id)

        assert len(setup.port.calls) == 1

    def test_completion_none_never_flushes(self) -> None:
        """completion 未注入 (flag OFF 相当) では何ターン経っても LLM を呼ばない。"""
        setup = _build_setup(outcome={"decisions": []}, completion=None, turn_interval=1)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        for _ in range(20):
            setup.coordinator.after_turn_completed(setup.player_id)

        assert setup.port.calls == []
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1


class TestFlushPlayerBatchAndFailure:
    """batch drain と LLM 失敗時の evidence 温存を検証する。"""

    def test_flush_player_batches_up_to_batch_size(self) -> None:
        """batch_size を超える evidence があっても 1 回の flush では上限件数だけ処理する。"""
        setup = _build_setup(outcome={"decisions": []}, batch_size=2)
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        for i in range(5):
            setup.evidence_buffer.append_by_being(
                setup.being_id,
                _evidence(f"e{i}", occurred_at=base + timedelta(minutes=i)),
            )

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 2
        remaining = [
            e.evidence_id for e in setup.evidence_buffer.list_all_by_being(setup.being_id)
        ]
        assert remaining == ["e2", "e3", "e4"]

    def test_llm_failure_keeps_evidence_for_next_cycle(self) -> None:
        """LLM 呼び出し失敗時は evidence を buffer に残し、次周期の再試行に委ねる。"""
        setup = _build_setup(outcome=LlmApiCallException("boom", error_code="LLM_ERROR"))
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 0
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1
        assert setup.semantic_store.list_for_being(setup.being_id) == []

    def test_unexpected_exception_also_keeps_evidence(self) -> None:
        """想定外の例外でも evidence を握りつぶさず buffer に残す。"""
        setup = _build_setup(outcome=RuntimeError("unexpected"))
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 0
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1

    def test_empty_buffer_is_noop(self) -> None:
        """evidence が無ければ LLM を呼ばず 0 を返す。"""
        setup = _build_setup(outcome={"decisions": []})

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 0
        assert setup.port.calls == []

    def test_empty_decisions_but_nonempty_batch_logs_warning(self, caplog) -> None:
        """LLM 呼び出しは成功したが適用された decision が 0 件のまま batch を drain
        するとき、evidence が静かに失われ続けないよう warning を 1 件出す。"""
        setup = _build_setup(outcome={"decisions": []})
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.belief_consolidation_coordinator",
        ):
            processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 1
        assert setup.evidence_buffer.list_all_by_being(setup.being_id) == []
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "0 件" in warnings[0].getMessage()

    def test_unresolved_being_is_noop(self) -> None:
        """Being 未 provision の player は silent no-op (turn を止めない)。"""
        setup = _build_setup(outcome={"decisions": []})
        unprovisioned_player = PlayerId(999)

        processed = setup.coordinator.flush_player(unprovisioned_player)

        assert processed == 0
        assert setup.port.calls == []


class TestHighSalienceBatchCap:
    """U6 (乱発対策): 1 batch に採用する salience=high evidence の上限。"""

    def test_high_salience_evidence_is_capped_per_batch(self) -> None:
        """high_salience_batch_cap を超える high evidence は次周期に残る。
        batch_size 自体には余裕を持たせ、cap が効いていることを見る。"""
        setup = _build_setup(
            outcome={"decisions": []},
            batch_size=8,
            high_salience_batch_cap=2,
        )
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        for i in range(4):
            setup.evidence_buffer.append_by_being(
                setup.being_id,
                _evidence(
                    f"high-{i}",
                    salience=BELIEF_EVIDENCE_SALIENCE_HIGH,
                    occurred_at=base + timedelta(minutes=i),
                ),
            )

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 2
        remaining = [
            e.evidence_id for e in setup.evidence_buffer.list_all_by_being(setup.being_id)
        ]
        assert remaining == ["high-2", "high-3"]

    def test_low_salience_evidence_fills_remaining_batch_slots(self) -> None:
        """high が cap で絞られても、low evidence は batch_size まで通常通り採る。"""
        setup = _build_setup(
            outcome={"decisions": []},
            batch_size=3,
            high_salience_batch_cap=1,
        )
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence("high-1", salience=BELIEF_EVIDENCE_SALIENCE_HIGH, occurred_at=base),
        )
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "high-2",
                salience=BELIEF_EVIDENCE_SALIENCE_HIGH,
                occurred_at=base + timedelta(minutes=1),
            ),
        )
        for i in range(2):
            setup.evidence_buffer.append_by_being(
                setup.being_id,
                _evidence(
                    f"low-{i}",
                    salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                    occurred_at=base + timedelta(minutes=2 + i),
                ),
            )

        processed = setup.coordinator.flush_player(setup.player_id)

        # high-1 (cap 内) + low-0 + low-1 の 3 件が採用され、high-2 は残る。
        assert processed == 3
        remaining = [
            e.evidence_id for e in setup.evidence_buffer.list_all_by_being(setup.being_id)
        ]
        assert remaining == ["high-2"]


class TestDecisionApplication:
    """decisions の各 action が belief journal に正しく反映されることを検証する。"""

    def test_create_adds_new_active_belief(self) -> None:
        """create decision で新規 active belief が 1 件追加される。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "この島の探索は空振りが多い",
                        "importance": 6,
                        "tags": ["explore"],
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        entries = setup.semantic_store.list_for_being(setup.being_id)
        assert len(entries) == 1
        assert entries[0].text == "この島の探索は空振りが多い"
        assert entries[0].status == SEMANTIC_MEMORY_STATUS_ACTIVE
        assert entries[0].support_evidence_ids == ("e1",)

    def test_multiple_same_kind_evidence_folds_into_single_create(self) -> None:
        """同一 batch 内の同型 evidence 3 件が 1 つの create に畳まれる (S1)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "この島の探索は空振りが多い",
                        "importance": 6,
                        "tags": ["explore"],
                        "evidence_ids": ["e1", "e2", "e3"],
                    }
                ]
            }
        )
        for i in range(3):
            setup.evidence_buffer.append_by_being(
                setup.being_id, _evidence(f"e{i+1}", cue_signature="tool:explore")
            )

        setup.coordinator.flush_player(setup.player_id)

        entries = setup.semantic_store.list_for_being(setup.being_id)
        assert len(entries) == 1
        assert set(entries[0].support_evidence_ids) == {"e1", "e2", "e3"}

    def test_create_initial_confidence_reflects_founding_evidence_count(self) -> None:
        """create した belief の初期 confidence は founding evidence 件数を反映する
        (support_evidence_ids を数えているのに base 固定なのは不整合)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "この島の探索は空振りが多い",
                        "importance": 6,
                        "tags": ["探索"],
                        "evidence_ids": ["e1", "e2"],
                    }
                ]
            }
        )
        for i in range(2):
            setup.evidence_buffer.append_by_being(setup.being_id, _evidence(f"e{i+1}"))

        setup.coordinator.flush_player(setup.player_id)

        entries = setup.semantic_store.list_for_being(setup.being_id)
        assert len(entries) == 1
        assert entries[0].confidence == compute_belief_confidence(2, 0)

    def test_create_mixes_cue_tokens_into_tags_for_self_consistent_shortlist(self) -> None:
        """日本語タグだけの create で作った belief でも、根拠 evidence の cue token
        (英語 tool token "explore") が tags に混ざるため、後続の別 tool:explore
        evidence が同じ belief を shortlist に載せられる (tool 軸の索引自己修復)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "この島の探索は空振りが多い",
                        "importance": 6,
                        "tags": ["探索"],  # 日本語タグのみ (LLM 出力想定)
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        )
        setup.evidence_buffer.append_by_being(
            setup.being_id, _evidence("e1", cue_signature="tool:explore")
        )

        setup.coordinator.flush_player(setup.player_id)

        created = setup.semantic_store.list_for_being(setup.being_id)[0]
        # cue token "explore" が tags に混ざっている
        assert "explore" in {t.lower() for t in created.tags}

        # 後続の別 tool:explore evidence の batch でこの belief が shortlist に載る
        shortlist = setup.coordinator._build_shortlist(
            setup.being_id,
            (_evidence("e2", cue_signature="tool:explore"),),
        )
        assert created.belief_id in {b.belief_id for b in shortlist}

    def test_strengthen_appends_support_and_recomputes_confidence(self) -> None:
        """strengthen decision で既存 belief の support_evidence_ids が増え、
        confidence がルール関数で再計算される。"""
        existing = _belief_entry(entry_id="sem-1", support=("old-e",))
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "strengthen",
                        "belief_id": "sem-1",
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        entries = setup.semantic_store.list_for_being(setup.being_id)
        assert len(entries) == 1
        updated = entries[0]
        assert updated.entry_id == "sem-1"
        assert set(updated.support_evidence_ids) == {"old-e", "e1"}
        assert updated.confidence == compute_belief_confidence(2, 0)

    def test_revise_supersedes_old_entry_and_keeps_belief_id(self) -> None:
        """revise decision で旧 entry が superseded になり、新 entry が同じ
        belief_id を引き継ぐ (原本は消えず想起からのみ外れる)。"""
        existing = _belief_entry(entry_id="sem-1", text="拠点に資源はない")
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "revise",
                        "belief_id": "sem-1",
                        "text": "拠点付近に資源が見つかることもある",
                        "reason": "反例が見つかった",
                    }
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        entries = {e.entry_id: e for e in setup.semantic_store.list_for_being(setup.being_id)}
        assert entries["sem-1"].status == SEMANTIC_MEMORY_STATUS_SUPERSEDED
        new_entries = [
            e
            for e in entries.values()
            if e.entry_id != "sem-1" and e.belief_id == "sem-1"
        ]
        assert len(new_entries) == 1
        assert new_entries[0].status == SEMANTIC_MEMORY_STATUS_ACTIVE
        assert new_entries[0].text == "拠点付近に資源が見つかることもある"
        assert new_entries[0].supersedes == "sem-1"

    def test_contradict_below_threshold_marks_inactive(self) -> None:
        """contradict の累積で confidence が閾値を割ると inactive になる
        (想起から消えるが削除はしない)。"""
        # support=0, contradict=0 → confidence = 0.4 (base)。閾値 0.2 を割るには
        # contradict を 2 件以上積む必要がある (0.4 - 0.15*2 = 0.1 < 0.2)。
        existing = _belief_entry(entry_id="sem-1", support=(), contradict=("old-c",))
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "contradict",
                        "belief_id": "sem-1",
                        "evidence_ids": ["e1"],
                    }
                ]
            },
            contradict_inactive_threshold=0.2,
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        entries = {e.entry_id: e for e in setup.semantic_store.list_for_being(setup.being_id)}
        assert entries["sem-1"].status == SEMANTIC_MEMORY_STATUS_INACTIVE
        assert set(entries["sem-1"].contradict_evidence_ids) == {"old-c", "e1"}

    def test_contradict_above_threshold_stays_active(self) -> None:
        """反証が 1 件だけなら confidence は閾値を割らず active のまま残る。"""
        existing = _belief_entry(entry_id="sem-1", support=("s1", "s2"))
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "contradict",
                        "belief_id": "sem-1",
                        "evidence_ids": ["e1"],
                    }
                ]
            },
            contradict_inactive_threshold=0.2,
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        entries = {e.entry_id: e for e in setup.semantic_store.list_for_being(setup.being_id)}
        assert entries["sem-1"].status == SEMANTIC_MEMORY_STATUS_ACTIVE

    def test_discard_leaves_journal_untouched_but_drains_evidence(self) -> None:
        """discard decision は journal に何も書かないが、evidence は batch drain で消える。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "discard",
                        "evidence_ids": ["e1"],
                        "reason": "一時的なタスクだった",
                    }
                ]
            }
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        assert setup.semantic_store.list_for_being(setup.being_id) == []
        assert setup.evidence_buffer.list_all_by_being(setup.being_id) == []

    def test_unresolvable_belief_id_is_ignored(self) -> None:
        """存在しない belief_id への strengthen/contradict/revise は無視され、
        例外にならない (batch drain 自体は正常に進む)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "strengthen",
                        "belief_id": "sem-unknown",
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 1
        assert setup.semantic_store.list_for_being(setup.being_id) == []


class TestShortlistDeterminism:
    """shortlist 選択の決定論性を検証する。"""

    def test_shortlist_picks_beliefs_matching_cue_tokens(self) -> None:
        """evidence の cue_signature 由来トークンと一致する tags/text を持つ belief だけが
        shortlist に載る。"""
        matching = _belief_entry(
            entry_id="sem-match", text="探索は空振りが多い", tags=("explore",)
        )
        unrelated = _belief_entry(
            entry_id="sem-unrelated", text="ノアは機嫌が悪いと無視する", tags=("ノア",)
        )
        setup = _build_setup(outcome={"decisions": []})
        setup.semantic_store.add_by_being(setup.being_id, matching)
        setup.semantic_store.add_by_being(setup.being_id, unrelated)
        setup.evidence_buffer.append_by_being(
            setup.being_id, _evidence("e1", cue_signature="tool:explore")
        )

        setup.coordinator.flush_player(setup.player_id)

        assert len(setup.port.calls) == 1
        user_message = setup.port.calls[0][1]["content"]
        assert "sem-match" in user_message
        assert "sem-unrelated" not in user_message

    def test_shortlist_is_deterministic_across_repeated_calls(self) -> None:
        """同じ入力なら shortlist の並びは常に同じ (LLM の非決定性を持ち込まない)。"""
        beliefs = [
            _belief_entry(entry_id=f"sem-{i}", text=f"探索の学び {i}", tags=("explore",))
            for i in range(3)
        ]
        setup = _build_setup(outcome={"decisions": []}, shortlist_top_k=2)
        for b in beliefs:
            setup.semantic_store.add_by_being(setup.being_id, b)
        setup.evidence_buffer.append_by_being(
            setup.being_id, _evidence("e1", cue_signature="tool:explore")
        )

        shortlist_1 = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )
        shortlist_2 = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        assert [b.belief_id for b in shortlist_1] == [b.belief_id for b in shortlist_2]
        assert len(shortlist_1) == 2

    def test_shortlist_empty_when_no_active_beliefs(self) -> None:
        """active belief が無ければ shortlist は空になる。"""
        setup = _build_setup(outcome={"decisions": []})
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        assert shortlist == ()


class TestShortlistAttribution:
    """U4 (予測誤差統一設計 部品3): in_context_belief_ids が指す belief は
    cue スコアに関わらず必ず shortlist に含まれること。"""

    def test_cue_スコアが0でも_in_context_belief_は必ず載る(self) -> None:
        """cue_signature がノアと無関係な belief でも、evidence の
        in_context_belief_ids に含まれていれば shortlist に強制搭載される。"""
        unrelated_but_in_context = _belief_entry(
            entry_id="sem-unrelated-in-context",
            text="ノアは機嫌が悪いと無視する",
            tags=("ノア",),
        )
        setup = _build_setup(outcome={"decisions": []})
        setup.semantic_store.add_by_being(setup.being_id, unrelated_but_in_context)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="tool:explore",
                in_context_belief_ids=("sem-unrelated-in-context",),
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        assert [b.belief_id for b in shortlist] == ["sem-unrelated-in-context"]

    def test_revise後の旧entry_idが_in_contextでも新active_beliefが必ず載る(
        self,
    ) -> None:
        """belief を create → revise (supersede) すると active entry の entry_id は
        新しい値になり belief_id だけ旧値を継ぐ。想起はその時点の entry_id を
        in_context_belief_ids に焼き込むため、revise 後に想起された belief は
        forced 照合が entry_id と belief_id の食い違いで永久に外れていた。
        entry_id → belief_id → 現在の active entry の系譜解決により、旧 entry_id を
        持つ evidence でも現在の active belief が forced で shortlist に載ること。"""
        original = _belief_entry(
            entry_id="sem-A",
            belief_id="sem-A",
            text="ノアは機嫌が悪いと無視する",
            tags=("ノア",),
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
        )
        revised = _belief_entry(
            entry_id="sem-B",
            belief_id="sem-A",
            text="ノアは機嫌が悪いと無視するが挨拶には応じる",
            tags=("ノア",),
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
        )
        setup = _build_setup(outcome={"decisions": []})
        setup.semantic_store.add_by_being(setup.being_id, original)
        # revise: 旧 sem-A を superseded にし、新 active sem-B (belief_id=sem-A) を追加。
        setup.semantic_store.supersede_by_being(
            setup.being_id, old_entry_id="sem-A", new_entry=revised
        )
        # 想起は revise 後の active entry の entry_id (=sem-B) を焼き込む。
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="tool:explore",
                in_context_belief_ids=("sem-B",),
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        assert [(b.entry_id, b.belief_id) for b in shortlist] == [("sem-B", "sem-A")]

    def test_存在しない_in_context_id_は例外にせず無視する(self) -> None:
        """in_context_belief_ids に active でも inactive でも存在しない id が
        含まれていても、例外を投げず単に forced 対象から外れること。"""
        matching = _belief_entry(
            entry_id="sem-match", text="探索は空振りが多い", tags=("explore",)
        )
        setup = _build_setup(outcome={"decisions": []})
        setup.semantic_store.add_by_being(setup.being_id, matching)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="tool:explore",
                in_context_belief_ids=("sem-does-not-exist",),
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        # 存在しない forced id は無視され、cue スコア一致の belief だけが残る。
        assert [b.belief_id for b in shortlist] == ["sem-match"]

    def test_in_context_belief_は_top_k_の_cap_を超えても全件残る(self) -> None:
        """forced (in-context) belief は top_k を超過しても全て残す。
        cue スコアベースの追加候補だけが残り枠に絞られる。"""
        forced_beliefs = [
            _belief_entry(entry_id=f"sem-forced-{i}", text=f"信念{i}", tags=("x",))
            for i in range(3)
        ]
        scored_belief = _belief_entry(
            entry_id="sem-scored", text="探索は空振りが多い", tags=("explore",)
        )
        setup = _build_setup(outcome={"decisions": []}, shortlist_top_k=2)
        for b in forced_beliefs:
            setup.semantic_store.add_by_being(setup.being_id, b)
        setup.semantic_store.add_by_being(setup.being_id, scored_belief)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="tool:explore",
                in_context_belief_ids=tuple(b.belief_id for b in forced_beliefs),
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        shortlist_ids = {b.belief_id for b in shortlist}
        assert shortlist_ids >= {b.belief_id for b in forced_beliefs}
        # top_k=2 を forced 3 件が既に超えているので、cue スコアの追加候補は
        # 残り枠 0 件で採用されない。
        assert "sem-scored" not in shortlist_ids

    def test_flag_OFF相当_in_context_belief_ids_が空なら従来どおりcueスコアのみ(
        self,
    ) -> None:
        """evidence.in_context_belief_ids が常に空 (U4 flag OFF) のときは
        forced belief が存在しないため、導入前と同じ cue スコアのみの
        shortlist になる。"""
        matching = _belief_entry(
            entry_id="sem-match", text="探索は空振りが多い", tags=("explore",)
        )
        setup = _build_setup(outcome={"decisions": []})
        setup.semantic_store.add_by_being(setup.being_id, matching)
        setup.evidence_buffer.append_by_being(
            setup.being_id, _evidence("e1", cue_signature="tool:explore")
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id, tuple(setup.evidence_buffer.list_all_by_being(setup.being_id))
        )

        assert [b.belief_id for b in shortlist] == ["sem-match"]


class TestSystemPromptConfirmationGating:
    """U4: CONFIRMATION 節の system prompt 追記が
    belief_attribution_enabled に連動すること (OFF なら pre-U4 と byte 一致)。"""

    def test_flag_OFF_なら_confirmation_節が_prompt_に無い(self) -> None:
        setup = _build_setup(
            outcome={"decisions": []}, belief_attribution_enabled=False
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert "confirmation" not in system_message

    def test_flag_ON_なら_confirmation_節が_prompt_に有る(self) -> None:
        setup = _build_setup(
            outcome={"decisions": []}, belief_attribution_enabled=True
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert "confirmation" in system_message

    def test_flag_OFF_の_system_prompt_は_pre_U4_定数と_byte_一致(self) -> None:
        """OFF のとき組み立てる system prompt が既定定数そのものであること
        (U1 で確立した flag 規律: OFF なら導入前とプロンプト byte 一致)。"""
        from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
            _SYSTEM_BELIEF_CONSOLIDATION_JSON,
        )

        setup = _build_setup(
            outcome={"decisions": []}, belief_attribution_enabled=False
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert system_message == _SYSTEM_BELIEF_CONSOLIDATION_JSON


class TestReviseOnStrengthenBehavior:
    """P2: 支持が積み上がったヘッジ文面の belief に対し、固着 LLM が

    strengthen ではなく revise を返したとき、旧ヘッジ文面が superseded に
    なり、新 entry が証拠に見合う強い文面 + 同一 belief_id を引き継ぐこと
    (= 本 PR が狙う「ヘッジ凍結の解除」の振る舞い)。stub が LLM 判断を代役
    する (revise-on-strengthen を選ぶのは実 LLM の仕事で、その適用結果を固定)。
    """

    def test_hedged_supported_belief_is_reworded_stronger_via_revise(self) -> None:
        # ヘッジ文面 + 支持 4 件の well-supported な既存 belief。
        existing = _belief_entry(
            entry_id="sem-hedge",
            text="干潟は危険かもしれない",
            tags=("干潟",),
            support=("s1", "s2", "s3", "s4"),
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "revise",
                        "belief_id": "sem-hedge",
                        "text": "干潟はしばしば危険だ",
                        "reason": "支持が積み上がったのでヘッジを外して言い直す",
                    }
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        entries = {
            e.entry_id: e
            for e in setup.semantic_store.list_for_being(setup.being_id)
        }
        # 旧ヘッジ文面は superseded (原本は消えず想起からのみ外れる)。
        assert entries["sem-hedge"].status == SEMANTIC_MEMORY_STATUS_SUPERSEDED
        assert entries["sem-hedge"].text == "干潟は危険かもしれない"
        # 新 entry は同一 belief_id を継ぎ、強い文面になっている。
        new_entries = [
            e
            for e in entries.values()
            if e.entry_id != "sem-hedge" and e.belief_id == "sem-hedge"
        ]
        assert len(new_entries) == 1
        new = new_entries[0]
        assert new.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        assert new.text == "干潟はしばしば危険だ"
        # ヘッジ語 (かもしれない) が消えている。
        assert "かもしれない" not in new.text

    def test_prompt_carries_revise_on_strengthen_guidance(self) -> None:
        """振る舞いを引き出す前提として、指示文が固着プロンプトに載っている

        ことを配線ガードとして固定する (実 LLM がこの指示を読む)。"""
        setup = _build_setup(outcome={"decisions": []})
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert "文面の強さを証拠に合わせる" in system_message
        assert "revise を選び" in system_message
        assert "支持が 3 件以上" in system_message
        # sup1-2 はヘッジを保つ、の較正指示も載っている。
        assert "ヘッジを保つ" in system_message


class TestTracePayload:
    """BELIEF_CONSOLIDATION trace の payload を検証する。"""

    def test_emits_trace_event_with_decisions(self) -> None:
        """flush 成功時に BELIEF_CONSOLIDATION trace が 1 件記録され、
        batch/shortlist/decisions が payload に残る。"""
        from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind

        recorder = NullTraceRecorder()
        captured: list = []
        original_record = recorder.record

        def _wrapper(kind, **kw):
            ev = original_record(kind, **kw)
            captured.append(ev)
            return ev

        recorder.record = _wrapper  # type: ignore[method-assign]

        repo = InMemoryBeingRepository()
        resolver = BeingAttachmentResolver(repo)
        provisioning = BeingProvisioningService(repo)
        player_id = PlayerId(7)
        being_id = provisioning.ensure_attached(player_id)
        evidence_buffer = InMemoryBeliefEvidenceBufferStore()
        semantic_store = InMemorySemanticMemoryStore()
        port = _FakeBeliefConsolidationPort(
            {
                "decisions": [
                    {
                        "action": "create",
                        "text": "この島の探索は空振りが多い",
                        "importance": 5,
                        "tags": [],
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        )
        coordinator = BeliefConsolidationCoordinator(
            evidence_buffer_store=evidence_buffer,
            semantic_store=semantic_store,
            completion=port,
            being_attachment_resolver=resolver,
            default_world_id=_WORLD_ID,
            trace_recorder_provider=lambda: recorder,
        )
        evidence_buffer.append_by_being(being_id, _evidence("e1"))

        coordinator.flush_player(player_id)

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_CONSOLIDATION]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["batch_evidence_ids"] == ["e1"]
        assert payload["decisions"][0]["action"] == "create"


class TestConfirmationSupportWeightApplication:
    """P3b: create / strengthen で CONFIRMATION 由来支持を内数として蓄積し、

    confidence に 0.5 重みが効くこと。"""

    def _active(self, setup):
        return [
            e
            for e in setup.semantic_store.list_for_being(setup.being_id)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]

    def test_create_from_confirmation_evidence_is_weighted_half(self) -> None:
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "浜辺では発見が少ない",
                        "importance": 4,
                        "tags": ["浜辺"],
                        "evidence_ids": ["e1"],
                    }
                ]
            }
        )
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence("e1", source_kind=BeliefEvidenceSourceKind.CONFIRMATION),
        )

        setup.coordinator.flush_player(setup.player_id)

        entries = self._active(setup)
        assert len(entries) == 1
        created = entries[0]
        # 支持1件すべて CONFIRMATION → 内数1、confidence は f(1,0,1)。
        assert created.confirmation_support_count == 1
        assert created.confidence == pytest.approx(
            compute_belief_confidence(1, 0, 1)
        )
        # 予測誤差1件で作った場合 (f(1,0,0)) より低い。
        assert created.confidence < compute_belief_confidence(1, 0, 0)

    def test_strengthen_accumulates_confirmation_count(self) -> None:
        existing = _belief_entry(
            entry_id="sem-b",
            text="浜辺では発見が少ない",
            tags=("浜辺",),
            support=("s-old",),  # 既存支持1 (非 CONFIRMATION)
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {"action": "strengthen", "belief_id": "sem-b", "evidence_ids": ["e1"]}
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence("e1", source_kind=BeliefEvidenceSourceKind.CONFIRMATION),
        )

        setup.coordinator.flush_player(setup.player_id)

        updated = self._active(setup)[0]
        # 支持2 (s-old + e1)、うち CONFIRMATION は e1 の1件。
        assert len(updated.support_evidence_ids) == 2
        assert updated.confirmation_support_count == 1
        assert updated.confidence == pytest.approx(
            compute_belief_confidence(2, 0, 1)
        )

    def test_strengthen_with_duplicate_evidence_ids_does_not_break_invariant(
        self,
    ) -> None:
        """LLM が同一 evidence_id を重複列挙しても strengthen が握りつぶされない。

        support は set 統合で 1 件しか増えないので、内数 (CONFIRMATION 件数) も
        1 に揃えないと ``confirmation + hearsay <= len(support)`` 不変条件を破り、
        SemanticMemoryEntry が例外を投げて strengthen が黙って捨てられる
        (evidence は drain されて失われる = 静かな失敗)。重複除去でこれを防ぐ。
        """
        existing = _belief_entry(
            entry_id="sem-dup",
            text="浜辺では発見が少ない",
            tags=("浜辺",),
            support=("s-old",),
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "strengthen",
                        "belief_id": "sem-dup",
                        # 同じ id を重複させた壊れ気味の LLM 出力。
                        "evidence_ids": ["e1", "e1"],
                    }
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence("e1", source_kind=BeliefEvidenceSourceKind.CONFIRMATION),
        )

        setup.coordinator.flush_player(setup.player_id)

        updated = self._active(setup)[0]
        # 重複は 1 件に畳まれ、support は s-old + e1 の 2 件、CONFIRMATION 内数 1。
        assert len(updated.support_evidence_ids) == 2
        assert updated.confirmation_support_count == 1
        assert updated.confidence == pytest.approx(compute_belief_confidence(2, 0, 1))

    def test_strengthen_resolves_whitespace_padded_evidence_id(self) -> None:
        """前後に空白のある evidence_id も strip して実在 evidence に解決する。

        strip 前の生 id を support に積むと、以後の内数カウントが
        ``evidence_by_id`` のキーと文字列一致せず過小評価される (軽微な不整合)。
        strip 済みの id を採用して buffer 上の evidence と一致させる。
        """
        existing = _belief_entry(
            entry_id="sem-ws", text="浜辺では発見が少ない", tags=("浜辺",), support=(),
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {"action": "strengthen", "belief_id": "sem-ws", "evidence_ids": ["  e1  "]}
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence("e1", source_kind=BeliefEvidenceSourceKind.CONFIRMATION),
        )

        setup.coordinator.flush_player(setup.player_id)

        updated = self._active(setup)[0]
        assert updated.support_evidence_ids == ("e1",)
        assert updated.confirmation_support_count == 1


class TestConfirmationWeightPreservedOnReviseContradict:
    """P3b 回帰: revise / contradict が confirmation_support_count を confidence

    再計算に渡し続けること。渡さないと 0.5 割引が消えて belief が再膨張する。
    confirmation_support_count>0 の target で検証する (0 値だと偶然一致して
    退行を見逃すため)。"""

    def _active(self, setup):
        return [
            e
            for e in setup.semantic_store.list_for_being(setup.being_id)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]

    def test_revise_preserves_confirmation_weight(self) -> None:
        # 支持4件すべて CONFIRMATION の belief (confidence は f(4,0,4)=0.6)。
        existing = _belief_entry(
            entry_id="sem-c",
            text="浜辺は安全かもしれない",
            support=("s1", "s2", "s3", "s4"),
            confirmation_support_count=4,
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "revise",
                        "belief_id": "sem-c",
                        "text": "浜辺はおおむね安全だ",
                        "reason": "言い直し",
                    }
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        new = [e for e in self._active(setup) if e.text == "浜辺はおおむね安全だ"][0]
        assert new.confirmation_support_count == 4
        # 重みが効いたまま (f(4,0,4)=0.6)。割引が消えると f(4,0,0)=0.8 になる。
        assert new.confidence == pytest.approx(compute_belief_confidence(4, 0, 4))
        assert new.confidence < compute_belief_confidence(4, 0, 0)

    def test_contradict_preserves_confirmation_weight(self) -> None:
        existing = _belief_entry(
            entry_id="sem-d",
            text="浜辺は安全かもしれない",
            support=("s1", "s2", "s3", "s4"),
            confirmation_support_count=4,
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {"action": "contradict", "belief_id": "sem-d", "evidence_ids": ["e1"]}
                ]
            }
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        updated = self._active(setup)[0]
        assert updated.confirmation_support_count == 4
        # 反証1を足し、かつ CONFIRMATION 重みを保つ (f(4,1,4))。
        assert updated.confidence == pytest.approx(compute_belief_confidence(4, 1, 4))
        # 割引が消えると f(4,1,0) になり高くなってしまう。
        assert updated.confidence < compute_belief_confidence(4, 1, 0)


class TestGoalReflect:
    """P4/P7: reflect の prompt 露出・停滞/達成/乖離の観測注入・種別ごとの cap・
    OFF 不変・goal store を書かない不変条件を保証する。"""

    def test_reflect_section_present_only_when_enabled(self) -> None:
        on = _build_setup(
            outcome={"decisions": []},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        on.evidence_buffer.append_by_being(on.being_id, _evidence("e1"))
        on.coordinator.flush_player(on.player_id)
        assert "reflect" in on.port.calls[0][0]["content"]

        off = _build_setup(outcome={"decisions": []}, goal_reflect_enabled=False)
        off.evidence_buffer.append_by_being(off.being_id, _evidence("e1"))
        off.coordinator.flush_player(off.player_id)
        # OFF は reflect 節が出ない (byte 不変)。
        assert "目的への前進評価" not in off.port.calls[0][0]["content"]

    def test_objective_text_in_prompt_when_provider_set(self) -> None:
        setup = _build_setup(
            outcome={"decisions": []},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂で狼煙を上げて救助される",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        user = setup.port.calls[0][0 + 1]["content"]  # [system, user]
        assert "山頂で狼煙を上げて救助される" in user

    def test_stalled_reflect_injects_observation(self) -> None:
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled",
                 "statement": "ふと振り返ると、この数日 山頂に一歩も近づいていない気がする"}
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(obs) == 1
        assert obs[0][0] == setup.player_id
        assert "山頂に一歩も近づいていない" in obs[0][1]

    def test_progressing_reflect_injects_nothing(self) -> None:
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "progressing", "statement": "順調だ"}
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert obs == []

    def test_reflect_ignored_when_flag_off(self) -> None:
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞"}
            ]},
            goal_reflect_enabled=False,
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert obs == []

    def test_stall_observation_capped_by_min_interval(self) -> None:
        """同一 player への停滞観測は min_interval turn 以内なら再注入しない。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
            stall_min_interval_turns=15,
        )
        # 1 回目: 注入される (turn 0)。
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        # 2 回目: turn を進めずに即 flush → cap で抑制。
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e2"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(obs) == 1

    def test_stall_observation_refires_after_min_interval(self) -> None:
        """cap の逆方向: min_interval turn を跨いだら停滞観測が再び注入される。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "また空回りしている"}
            ]},
            # auto-flush を止め、flush を手動で駆動する (turn 進行と分離)。
            turn_interval=10_000,
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
            stall_min_interval_turns=15,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)  # turn 0 で注入
        # 15 turn 経過させる (cap を跨ぐ)。
        for _ in range(15):
            setup.coordinator.after_turn_completed(setup.player_id)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e2"))
        setup.coordinator.flush_player(setup.player_id)  # turn 15 で再注入
        assert len(obs) == 2

    def test_goal_reflect_enabled_requires_provider_and_sink(self) -> None:
        """fail-fast: goal_reflect ON なのに provider / sink が欠けると構築時に落ちる。

        「reflect 節を出しておいて発火した reflect を黙って捨てる」静かな失敗を
        起動時に構造で弾く。"""
        with pytest.raises(ValueError, match="objective_text_provider"):
            _build_setup(
                outcome={"decisions": []},
                goal_reflect_enabled=True,
                reflect_observation_sink=lambda pid, msg, verdict: None,
            )
        with pytest.raises(ValueError, match="reflect_observation_sink"):
            _build_setup(
                outcome={"decisions": []},
                goal_reflect_enabled=True,
                objective_text_provider=lambda pid: "山頂へ行く",
            )

    def test_reflect_section_lists_three_verdicts_when_enabled(self) -> None:
        """P7: ON のとき reflect 節に停滞/達成/乖離の 3 種が提示される。"""
        setup = _build_setup(
            outcome={"decisions": []},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        system = setup.port.calls[0][0]["content"]
        assert "stalled" in system
        assert "achieved" in system
        assert "misaligned" in system

    def test_achieved_reflect_injects_observation_with_verdict(self) -> None:
        """P7: 達成の気づきが verdict 種別つきで内省観測として注入される。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "achieved",
                 "statement": "気づけば、探していた地図はもう手に入れている"}
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "古い地図を手に入れる",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(obs) == 1
        assert obs[0][2] == "achieved"
        assert "地図はもう手に入れている" in obs[0][1]

    def test_misaligned_reflect_injects_observation_with_verdict(self) -> None:
        """P7: 乖離 (目的から逸れている) の気づきが verdict つきで注入される。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "misaligned",
                 "statement": "気づけば釣りに夢中で、山頂のことをすっかり忘れていた"}
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(obs) == 1
        assert obs[0][2] == "misaligned"

    def test_cap_is_per_verdict_kind(self) -> None:
        """P7: cap は種別ごと。直近に停滞を出しても、達成の気づきは別枠で注入される。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "空回りしている"},
                {"action": "reflect", "verdict": "achieved", "statement": "もう果たしている"},
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
            stall_min_interval_turns=15,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        kinds = sorted(o[2] for o in obs)
        assert kinds == ["achieved", "stalled"]

    def test_reflect_coordinator_holds_no_goal_store_reference(self) -> None:
        """P7 不変条件: 固着 coordinator は goal store への参照を一切持たない。

        reflect が達成と判断しても goal store の status を変えられない ——
        参照が無いこと自体で「無意識は書かない、意識が決断する」を構造保証する。
        本テストは属性名の照合による補助的な早期検知にすぎない (別名を付ければ
        すり抜けられる)。不変条件の実効的な保証は「書き込み経路が配線上存在しない
        こと」であり、それは integration test
        ``test_reflect_observation_does_not_mutate_goal_store`` が達成観測を実経路で
        注入しても goal が active のまま変わらないことで固定している。
        """
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "achieved", "statement": "果たした"}
            ]},
            goal_reflect_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        # goal store / journal / repository を指す参照が無いこと (bool フラグ
        # _goal_reflect_enabled は保持を意味しないので除外)。
        attrs = vars(setup.coordinator)
        offending = [
            name for name in attrs
            if any(k in name.lower() for k in ("journal", "goal_store", "goal_repo"))
        ]
        assert offending == []


class TestGoalStagnationEvidence:
    """P-U1: reflect の stalled/misaligned verdict を goal: 軸の高 salience
    PREDICTION_ERROR evidence として buffer に積む挙動と、その不変条件
    (停滞 ≠ 即改訂 / goal store を触らない) を保証する。"""

    def _goal_axis_evidence(self, setup) -> list[BeliefEvidence]:
        return [
            e
            for e in setup.evidence_buffer.list_all_by_being(setup.being_id)
            if e.cue_signature.startswith("goal:")
        ]

    def test_stalled_verdict_pushes_one_high_salience_goal_evidence(self) -> None:
        """stalled → goal: 軸・高 salience・PREDICTION_ERROR の evidence が 1 件積まれる。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled",
                 "statement": "同じ場所を空回りしている気がする"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)

        # 観測は従来どおり注入される (P4/P7 の挙動を壊さない)。
        assert len(obs) == 1
        goal_evidences = self._goal_axis_evidence(setup)
        assert len(goal_evidences) == 1
        pushed = goal_evidences[0]
        assert pushed.cue_signature == "goal:山頂へ行く"
        assert pushed.salience == BELIEF_EVIDENCE_SALIENCE_HIGH
        assert pushed.source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR

    def test_achieved_verdict_pushes_no_evidence(self) -> None:
        """achieved (前進) は誤差ではないので evidence を積まない。"""
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "achieved", "statement": "もう果たした"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)

        assert self._goal_axis_evidence(setup) == []

    def test_misaligned_verdict_pushes_one_goal_evidence(self) -> None:
        """misaligned (目的と行動の乖離) も stalled と同じく evidence を 1 件積む。"""
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "misaligned",
                 "statement": "釣りに夢中で山頂のことを忘れていた"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)

        goal_evidences = self._goal_axis_evidence(setup)
        assert len(goal_evidences) == 1

    def test_flag_off_pushes_no_evidence_even_when_stalled(self) -> None:
        """GOAL_STAGNATION_EVIDENCE_ENABLED が OFF (既定) なら、stalled でも
        evidence を積まない = 導入前と完全に一致する。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=False,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)

        # 観測注入は変わらず発生するが、evidence は 1 件も積まれない。
        assert len(obs) == 1
        assert self._goal_axis_evidence(setup) == []

    def test_suppressed_by_cap_pushes_no_evidence(self) -> None:
        """観測注入自体が stall_min_interval_turns の cap で抑制された回は、
        evidence も積まない (「reflect が実際に発火したときだけ」乱発防止を
        観測と evidence で共有する)。

        2 回目の flush では 1 回目に積んだ goal: evidence が batch に含まれ
        (0 applied でも batch は 1 単位で drain される既存仕様のため) 一緒に
        drain されてしまい、buffer の最終件数だけでは「2 回目に新規で積んだか」
        を判定できない。そのため ``append_by_being`` 呼び出し自体をスパイして
        goal: 軸 evidence の**追加回数**を直接数える。
        """
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
            stall_min_interval_turns=15,
        )
        appended_goal_cues: list[str] = []
        original_append = setup.evidence_buffer.append_by_being

        def _spy_append(being_id, evidence) -> None:
            if evidence.cue_signature.startswith("goal:"):
                appended_goal_cues.append(evidence.cue_signature)
            original_append(being_id, evidence)

        setup.evidence_buffer.append_by_being = _spy_append

        # 1 回目: 注入 + evidence 1 件が積まれる。
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(appended_goal_cues) == 1

        # 2 回目: turn を進めずに即 flush → cap で観測が抑制され、evidence も
        # 追加で積まれない (呼び出し回数が増えない)。
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e2"))
        setup.coordinator.flush_player(setup.player_id)

        assert len(obs) == 1
        assert len(appended_goal_cues) == 1

    def test_reflect_does_not_write_belief_journal_directly(self) -> None:
        """不変条件: evidence 化を導入しても、reflect 自体は belief journal
        (semantic_store) に直接書き込まない。積むのは evidence buffer だけで、
        journal への反映は次周期以降の固着 LLM の判断を経由する。"""
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)

        assert setup.semantic_store.list_for_being(setup.being_id) == []
        # goal store / journal への参照を持たないという既存不変条件も併せて確認する。
        attrs = vars(setup.coordinator)
        offending = [
            name for name in attrs
            if any(k in name.lower() for k in ("journal", "goal_store", "goal_repo"))
        ]
        assert offending == []

    def test_goal_stagnation_evidence_requires_goal_reflect_enabled(self) -> None:
        """fail-fast: goal_stagnation_evidence だけ ON にして goal_reflect が
        OFF だと構築時に落ちる (reflect が発火せず evidence 化の対象が永遠に
        生まれない「flag を立てたのに何も起きない」静かな失敗を防ぐ)。"""
        with pytest.raises(ValueError, match="goal_reflect_enabled"):
            _build_setup(
                outcome={"decisions": []},
                goal_reflect_enabled=False,
                goal_stagnation_evidence_enabled=True,
            )

    def test_pushed_evidence_consolidates_into_goal_belief(self) -> None:
        """統合: 積んだ goal: evidence が次周期の固着 LLM 判断で belief 化される
        (「この方針は目的に前進しない」型の goal: belief 形成を狙う経路の確認)。
        """
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            goal_stagnation_evidence_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        # 1 周期目: reflect が発火し goal: evidence が 1 件積まれる (journal は空)。
        setup.coordinator.flush_player(setup.player_id)
        assert self._goal_axis_evidence(setup) != []
        assert setup.semantic_store.list_for_being(setup.being_id) == []

        # 2 周期目: 固着 LLM が積まれた goal: evidence を create に変換する
        # (evidence_ids 未指定 = batch 全体を根拠とみなす仕様を利用)。
        setup.port.outcome = {
            "decisions": [
                {
                    "action": "create",
                    "text": "山頂へ行くのは前進しない",
                    "importance": 7,
                    "tags": ["goal"],
                }
            ]
        }
        setup.coordinator.flush_player(setup.player_id)

        active = [
            e
            for e in setup.semantic_store.list_for_being(setup.being_id)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]
        assert len(active) == 1
        assert active[0].text == "山頂へ行くのは前進しない"


class TestStagnationPressure:
    """P-U2: reflect verdict を「停滞感」カウンタに畳み込む挙動を保証する。

    P-U1 (goal: evidence 化) とは独立した経路であり、cap (乱発防止) と
    無関係にカウンタが動く点が evidence 化との核心的な違い。"""

    def test_stalled_verdict_increments_counter(self) -> None:
        """stalled → カウンタが 0 から 1 になる。"""
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "空回りしている"}
            ]},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert setup.stagnation_pressure_store.get_by_being(setup.being_id) == 1

    def test_misaligned_verdict_increments_counter(self) -> None:
        """misaligned も stalled と同じくカウンタを +1 する。"""
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "misaligned", "statement": "逸れている"}
            ]},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert setup.stagnation_pressure_store.get_by_being(setup.being_id) == 1

    def test_achieved_verdict_resets_counter(self) -> None:
        """achieved (前進) は、それまで積み上がったカウンタを 0 に戻す。"""
        store = InMemoryStagnationPressureStore()
        being_id_holder: list = []

        # 1 周期目: stalled でカウンタを 2 まで積む。
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "空回りしている"}
            ]},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
            stagnation_pressure_store=store,
            turn_interval=10_000,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        for _ in range(20):
            setup.coordinator.after_turn_completed(setup.player_id)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e2"))
        setup.coordinator.flush_player(setup.player_id)
        assert store.get_by_being(setup.being_id) == 2

        # 2 周期目: achieved でリセットされる。
        setup.port.outcome = {
            "decisions": [
                {"action": "reflect", "verdict": "achieved", "statement": "もう果たした"}
            ]
        }
        for _ in range(20):
            setup.coordinator.after_turn_completed(setup.player_id)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e3"))
        setup.coordinator.flush_player(setup.player_id)
        assert store.get_by_being(setup.being_id) == 0

    def test_no_verdict_leaves_counter_unchanged(self) -> None:
        """reflect action が無い (verdict も無い) 回はカウンタを据え置く。"""
        setup = _build_setup(
            outcome={"decisions": []},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert setup.stagnation_pressure_store.get_by_being(setup.being_id) == 0

    def test_counter_still_increments_when_observation_suppressed_by_cap(self) -> None:
        """cap (stall_min_interval_turns) で観測注入自体が抑制された回でも、
        verdict が stalled ならカウンタは増える。

        cap は「同じ気づきを本人に何度も見せない」ための表示側の間引きであって
        「まだ停滞しているか」の判定ではない、という P-U2 の核心的な設計判断を
        直接保証するテスト。"""
        obs: list = []
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: obs.append((pid, msg, verdict)),
            stall_min_interval_turns=15,
        )
        # 1 回目: 観測が注入され、カウンタも 1 になる。
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(obs) == 1
        assert setup.stagnation_pressure_store.get_by_being(setup.being_id) == 1

        # 2 回目: turn を進めずに即 flush → 観測は cap で抑制されるが、
        # verdict は stalled のままなのでカウンタは 2 になる。
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e2"))
        setup.coordinator.flush_player(setup.player_id)
        assert len(obs) == 1
        assert setup.stagnation_pressure_store.get_by_being(setup.being_id) == 2

    def test_flag_off_leaves_counter_untouched_even_when_stalled(self) -> None:
        """STAGNATION_PRESSURE_ENABLED が OFF (既定) なら、stalled でもカウンタは
        動かない (= 導入前と完全に一致する)。"""
        store = InMemoryStagnationPressureStore()
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=False,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
            stagnation_pressure_store=store,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert store.get_by_being(setup.being_id) == 0

    def test_stagnation_pressure_requires_goal_reflect_enabled(self) -> None:
        """fail-fast: stagnation_pressure だけ ON にして goal_reflect が OFF だと
        構築時に落ちる (reflect が発火せずカウンタを動かす verdict が永遠に
        生まれない「flag を立てたのに何も起きない」静かな失敗を防ぐ)。"""
        with pytest.raises(ValueError, match="goal_reflect_enabled"):
            _build_setup(
                outcome={"decisions": []},
                goal_reflect_enabled=False,
                stagnation_pressure_enabled=True,
            )

    def test_stagnation_pressure_requires_store(self) -> None:
        """fail-fast: stagnation_pressure_enabled だけ ON にして store を渡さない
        (None) と構築時に落ちる。"""
        with pytest.raises(ValueError, match="stagnation_pressure_store"):
            _build_setup(
                outcome={"decisions": []},
                goal_reflect_enabled=True,
                objective_text_provider=lambda pid: "山頂へ行く",
                reflect_observation_sink=lambda pid, msg, verdict: None,
                stagnation_pressure_enabled=True,
                stagnation_pressure_store=None,
            )

    def test_stagnation_pressure_does_not_write_belief_journal_or_goal_store(self) -> None:
        """不変条件: 停滞感カウンタの畳み込みは belief journal にも goal store にも
        書き込まない。積むのは stagnation_pressure_store のカウンタのみ。"""
        setup = _build_setup(
            outcome={"decisions": [
                {"action": "reflect", "verdict": "stalled", "statement": "停滞している"}
            ]},
            goal_reflect_enabled=True,
            stagnation_pressure_enabled=True,
            objective_text_provider=lambda pid: "山頂へ行く",
            reflect_observation_sink=lambda pid, msg, verdict: None,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.coordinator.flush_player(setup.player_id)
        assert setup.semantic_store.list_for_being(setup.being_id) == []
        attrs = vars(setup.coordinator)
        offending = [
            name for name in attrs
            if any(k in name.lower() for k in ("journal", "goal_store", "goal_repo"))
        ]
        assert offending == []


class TestHearsaySupportWeightApplication:
    """P10: create / strengthen で HEARSAY 由来支持を内数として蓄積し、confidence
    に 0.5 重みが効くこと (伝聞だけで生まれた belief は直接体験由来より低い)。"""

    def _active(self, setup):
        return [
            e
            for e in setup.semantic_store.list_for_being(setup.being_id)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]

    def test_create_from_hearsay_evidence_is_weighted_half(self) -> None:
        """伝聞 evidence 1 件で作った belief は hearsay 内数 1、confidence が
        直接体験 1 件由来 (f(1,0,0,0)) より低い (設計メモ §4)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "エイダは釣りの名人だ",
                        "importance": 4,
                        "tags": ["エイダ"],
                        "evidence_ids": ["e1"],
                    }
                ]
            },
            hearsay_enabled=True,
        )
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                source_speaker="リオ",
            ),
        )

        setup.coordinator.flush_player(setup.player_id)

        entries = self._active(setup)
        assert len(entries) == 1
        created = entries[0]
        assert created.hearsay_support_count == 1
        assert created.confidence == pytest.approx(
            compute_belief_confidence(1, 0, 0, 1)
        )
        assert created.confidence < compute_belief_confidence(1, 0, 0, 0)

    def test_strengthen_accumulates_hearsay_count(self) -> None:
        """既存支持 1 (直接体験) の belief に伝聞支持を足すと hearsay 内数が 1 に
        増え、confidence 計算に 0.5 重みが反映される。"""
        existing = _belief_entry(
            entry_id="sem-b",
            text="エイダは釣りの名人だ",
            tags=("エイダ",),
            support=("s-old",),  # 既存支持1 (非 HEARSAY)
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {"action": "strengthen", "belief_id": "sem-b", "evidence_ids": ["e1"]}
                ]
            },
            hearsay_enabled=True,
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                source_speaker="リオ",
            ),
        )

        setup.coordinator.flush_player(setup.player_id)

        updated = self._active(setup)[0]
        assert len(updated.support_evidence_ids) == 2
        assert updated.hearsay_support_count == 1
        assert updated.confidence == pytest.approx(
            compute_belief_confidence(2, 0, 0, 1)
        )


class TestHearsayWeightPreservedOnReviseContradict:
    """P10 回帰: revise / contradict が hearsay_support_count を confidence 再計算に
    渡し続けること。渡さないと 0.5 割引が消えて belief が再膨張する。"""

    def _active(self, setup):
        return [
            e
            for e in setup.semantic_store.list_for_being(setup.being_id)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]

    def test_revise_preserves_hearsay_weight(self) -> None:
        existing = _belief_entry(
            entry_id="sem-c",
            text="北の泉は安全らしい",
            support=("s1", "s2", "s3", "s4"),
            hearsay_support_count=4,
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "revise",
                        "belief_id": "sem-c",
                        "text": "北の泉は安全だ",
                        "reason": "言い直し",
                    }
                ]
            },
            hearsay_enabled=True,
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        new = [e for e in self._active(setup) if e.text == "北の泉は安全だ"][0]
        assert new.hearsay_support_count == 4
        assert new.confidence == pytest.approx(compute_belief_confidence(4, 0, 0, 4))
        assert new.confidence < compute_belief_confidence(4, 0, 0, 0)

    def test_contradict_preserves_hearsay_weight(self) -> None:
        existing = _belief_entry(
            entry_id="sem-d",
            text="北の泉は安全らしい",
            support=("s1", "s2", "s3", "s4"),
            hearsay_support_count=4,
        )
        setup = _build_setup(
            outcome={
                "decisions": [
                    {"action": "contradict", "belief_id": "sem-d", "evidence_ids": ["e1"]}
                ]
            },
            hearsay_enabled=True,
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        updated = self._active(setup)[0]
        assert updated.hearsay_support_count == 4
        assert updated.confidence == pytest.approx(compute_belief_confidence(4, 1, 0, 4))


class TestHearsaySpeakerShortlist:
    """P10: 伝聞 evidence の話者 (source_speaker) についての人物 belief が、cue
    スコアに関わらず必ず shortlist に載ること (話者を信じるかの判断材料)。"""

    def test_speaker_belief_is_forced_into_shortlist(self) -> None:
        """cue が話者と無関係でも、話者名が text/tags に現れる人物 belief は
        shortlist に強制搭載される。"""
        speaker_belief = _belief_entry(
            entry_id="sem-rio",
            text="リオは人の話をちゃんと聞かない",
            tags=("リオ",),
        )
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=True)
        setup.semantic_store.add_by_being(setup.being_id, speaker_belief)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="spot:12",  # 話者と無関係な cue
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                source_speaker="リオ",
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id,
            tuple(setup.evidence_buffer.list_all_by_being(setup.being_id)),
        )

        assert "sem-rio" in {b.belief_id for b in shortlist}

    def test_non_speaker_belief_not_forced(self) -> None:
        """話者名を含まない belief は (cue も一致しなければ) 強制搭載されない。"""
        other = _belief_entry(
            entry_id="sem-other",
            text="エイダは頼りになる",
            tags=("エイダ",),
        )
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=True)
        setup.semantic_store.add_by_being(setup.being_id, other)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="spot:12",
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                source_speaker="リオ",
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id,
            tuple(setup.evidence_buffer.list_all_by_being(setup.being_id)),
        )

        assert "sem-other" not in {b.belief_id for b in shortlist}

    def test_speaker_belief_not_forced_when_flag_off(self) -> None:
        """flag OFF なら、batch に HEARSAY evidence が残留していても話者強制は
        発火しない (flag OFF = pre-P10 挙動一致を batch 残留物に依存せず保証)。"""
        speaker_belief = _belief_entry(
            entry_id="sem-rio",
            text="リオは人の話をちゃんと聞かない",
            tags=("リオ",),
        )
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=False)
        setup.semantic_store.add_by_being(setup.being_id, speaker_belief)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                cue_signature="spot:12",
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                source_speaker="リオ",
            ),
        )

        shortlist = setup.coordinator._build_shortlist(
            setup.being_id,
            tuple(setup.evidence_buffer.list_all_by_being(setup.being_id)),
        )

        assert "sem-rio" not in {b.belief_id for b in shortlist}


class TestSystemPromptHearsayGating:
    """P10: 伝聞節の system prompt 追記が hearsay_enabled に連動すること
    (OFF なら pre-P10 と byte 一致)。"""

    def test_hearsay_section_absent_when_flag_off(self) -> None:
        """flag OFF なら伝聞節が system prompt に出ない。"""
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=False)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert "hearsay" not in system_message
        assert "伝聞" not in system_message

    def test_hearsay_section_present_when_flag_on(self) -> None:
        """flag ON なら伝聞節が system prompt に出る。"""
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=True)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert "hearsay" in system_message
        assert "伝聞" in system_message

    def test_system_prompt_byte_identical_to_pre_p10_when_flag_off(self) -> None:
        """flag OFF のとき system prompt が pre-P10 定数と byte 一致する。"""
        from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
            _SYSTEM_BELIEF_CONSOLIDATION_JSON,
        )

        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=False)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        system_message = setup.port.calls[0][0]["content"]
        assert system_message == _SYSTEM_BELIEF_CONSOLIDATION_JSON


class TestHearsayEvidencePayloadSpeaker:
    """P10 回帰: evidence payload に source_speaker が載ること。

    _HEARSAY_INSTRUCTION は「source_speaker がその話者」と LLM に約束しているが、
    配線 (_build_messages) が実際にそのキーを渡していないと、話者ごとの文脈信頼
    判断が構造的に不可能になる (予測誤差記憶システムの横断レビュー C-1)。
    """

    def test_hearsay_evidence_payload_includes_source_speaker(self) -> None:
        """HEARSAY evidence (source_speaker="リオ") を含む batch を flush すると、
        completion port に渡る user メッセージの JSON に
        ``"source_speaker": "リオ"`` が含まれる。"""
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=True)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                source_speaker="リオ",
            ),
        )

        setup.coordinator.flush_player(setup.player_id)

        user_message = setup.port.calls[0][1]["content"]
        payload = json.loads(user_message.split("\n", 1)[1])
        evidence_payload = payload["evidence"][0]
        assert evidence_payload["source_speaker"] == "リオ"

    def test_non_hearsay_evidence_payload_omits_source_speaker_key(self) -> None:
        """source_speaker を持たない (None の) evidence では、payload に
        ``source_speaker`` キー自体が載らない (ノイズを避けるため非 None のときだけ
        条件付きで足す)。"""
        setup = _build_setup(outcome={"decisions": []}, hearsay_enabled=True)
        setup.evidence_buffer.append_by_being(
            setup.being_id,
            _evidence(
                "e1",
                source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
            ),
        )

        setup.coordinator.flush_player(setup.player_id)

        user_message = setup.port.calls[0][1]["content"]
        payload = json.loads(user_message.split("\n", 1)[1])
        evidence_payload = payload["evidence"][0]
        assert "source_speaker" not in evidence_payload


class _CapturingRecorder:
    """record を横取りして払い出した TraceEvent を蓄える簡易 recorder。"""

    def __init__(self) -> None:
        from ai_rpg_world.application.trace import NullTraceRecorder

        self._inner = NullTraceRecorder()
        self.events: list = []

    def record(self, kind, **kw):
        ev = self._inner.record(kind, **kw)
        self.events.append(ev)
        return ev

    def close(self) -> None:
        self._inner.close()


class TestEvidenceIdFallbackScopedToCreate:
    """H2: evidence_ids 未指定/全滅時の batch 全件フォールバックを create のみに
    限定し、strengthen / contradict では decision ごと skip すること。"""

    def test_contradict_without_evidence_ids_is_skipped_and_belief_unchanged(
        self,
    ) -> None:
        """contradict に evidence_ids が無いと decision ごと skip され、対象 belief の
        confidence も status も変わらない (修正前は batch 全件が反証計上され一撃で
        inactive になっていた)。batch は従来どおり drain される。"""
        # support=0 / contradict=1 → confidence f(0,1)=0.25 (閾値 0.2 超で active)。
        # 修正前は e1 が反証に加わり f(0,2)=0.10 < 0.2 で inactive 化していた。
        existing = _belief_entry(entry_id="sem-1", support=(), contradict=("old-c",))
        setup = _build_setup(
            outcome={"decisions": [{"action": "contradict", "belief_id": "sem-1"}]},
            contradict_inactive_threshold=0.2,
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 1
        entries = {
            e.entry_id: e for e in setup.semantic_store.list_for_being(setup.being_id)
        }
        assert entries["sem-1"].status == SEMANTIC_MEMORY_STATUS_ACTIVE
        assert entries["sem-1"].contradict_evidence_ids == ("old-c",)
        assert entries["sem-1"].confidence == compute_belief_confidence(0, 1)

    def test_strengthen_with_only_hallucinated_evidence_ids_is_skipped(self) -> None:
        """strengthen の evidence_ids が全て batch に無い幻覚 id なら decision ごと
        skip され、belief の support も confidence も変わらない (修正前は batch 全件が
        support に混入し confidence が水増しされていた)。"""
        existing = _belief_entry(entry_id="sem-1", support=("old-e",))
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "strengthen",
                        "belief_id": "sem-1",
                        "evidence_ids": ["ghost-1", "ghost-2"],
                    }
                ]
            },
        )
        setup.semantic_store.add_by_being(setup.being_id, existing)
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 1
        updated = setup.semantic_store.list_for_being(setup.being_id)[0]
        assert updated.support_evidence_ids == ("old-e",)
        assert updated.confidence == compute_belief_confidence(1, 0)

    def test_create_without_evidence_ids_still_uses_whole_batch(self) -> None:
        """create は evidence_ids 未指定でも従来どおり batch 全件を根拠に belief を
        作れる (H2 の限定は create には及ばない = 回帰防止)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "create",
                        "text": "この島の探索は空振りが多い",
                        "importance": 5,
                        "tags": [],
                    }
                ]
            },
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e2"))

        setup.coordinator.flush_player(setup.player_id)

        entries = setup.semantic_store.list_for_being(setup.being_id)
        assert len(entries) == 1
        assert set(entries[0].support_evidence_ids) == {"e1", "e2"}


class TestSkippedDecisionVisibility:
    """H3: 適用できなかった decision を skip 理由つきで分類し、trace payload と
    warning で可視化すること (適用済みの顔で消える学びを見えるようにする)。"""

    def test_skipped_decisions_emit_warning_with_being_and_count(
        self, caplog
    ) -> None:
        """存在しない belief_id への strengthen は skip され、被 being と件数を
        含む warning が 1 行出る (静かに消えない)。"""
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "strengthen",
                        "belief_id": "sem-ghost",
                        "evidence_ids": ["e1"],
                    }
                ]
            },
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        with caplog.at_level(logging.WARNING):
            setup.coordinator.flush_player(setup.player_id)

        skip_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "skip" in r.getMessage()
        ]
        assert len(skip_warnings) == 1
        msg = skip_warnings[0].getMessage()
        assert str(setup.being_id.value) in msg
        assert "1件" in msg

    def test_trace_payload_carries_skipped_decisions_with_reason(self) -> None:
        """skip した decision が BELIEF_CONSOLIDATION trace の skipped_decisions に
        理由つきで載る (幻覚 belief_id への strengthen なら strengthen_belief_not_found)。"""
        recorder = _CapturingRecorder()
        setup = _build_setup(
            outcome={
                "decisions": [
                    {
                        "action": "strengthen",
                        "belief_id": "sem-ghost",
                        "evidence_ids": ["e1"],
                    }
                ]
            },
            trace_recorder_provider=lambda: recorder,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        from ai_rpg_world.application.trace import TraceEventKind

        events = [
            e
            for e in recorder.events
            if e.kind == TraceEventKind.BELIEF_CONSOLIDATION
        ]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["decisions"] == []
        assert len(payload["skipped_decisions"]) == 1
        assert payload["skipped_decisions"][0]["reason"] == "strengthen_belief_not_found"


class TestMalformedResponseHandling:
    """M4: 例外なしの構造不正応答は LLM 例外と同格に扱い、buffer を温存して
    次周期に再試行すること (正当な空 decisions の drain とは区別する)。"""

    def test_malformed_decisions_string_preserves_buffer_and_retries(self) -> None:
        """decisions が list でない (文字列) 応答は drain せず buffer を温存し、
        次の flush で再び LLM に問い合わせる (修正前は空 list 扱いで全 drain された)。"""
        setup = _build_setup(outcome={"decisions": "これは配列ではない"})
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 0
        assert len(setup.port.calls) == 1
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1
        assert setup.semantic_store.list_for_being(setup.being_id) == []

        # 次周期: buffer が残っているので再び LLM を呼ぶ (再試行)。
        processed_again = setup.coordinator.flush_player(setup.player_id)

        assert processed_again == 0
        assert len(setup.port.calls) == 2
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1

    def test_non_dict_response_preserves_buffer(self) -> None:
        """dict ですらない応答 (list) も構造不正として buffer を温存する。"""
        setup = _build_setup(outcome=["not", "a", "dict"])  # type: ignore[arg-type]
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 0
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1

    def test_missing_decisions_key_preserves_buffer(self) -> None:
        """decisions キーを欠いた dict も構造不正として温存する (空 list とは別)。"""
        setup = _build_setup(outcome={"foo": "bar"})
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 0
        assert len(setup.evidence_buffer.list_all_by_being(setup.being_id)) == 1

    def test_valid_empty_decisions_still_drains(self) -> None:
        """正当な空 decisions ([]) は従来どおり batch を drain する
        (構造不正の温存とは区別する回帰テスト)。"""
        setup = _build_setup(outcome={"decisions": []})
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        processed = setup.coordinator.flush_player(setup.player_id)

        assert processed == 1
        assert setup.evidence_buffer.list_all_by_being(setup.being_id) == []

    def test_malformed_response_emits_note_trace_not_consolidation(self) -> None:
        """構造不正のときは NOTE trace が出て、BELIEF_CONSOLIDATION (batch 処理済み
        の記録) は出ない (温存した局面を trace 上で区別する)。"""
        recorder = _CapturingRecorder()
        setup = _build_setup(
            outcome={"decisions": "壊れている"},
            trace_recorder_provider=lambda: recorder,
        )
        setup.evidence_buffer.append_by_being(setup.being_id, _evidence("e1"))

        setup.coordinator.flush_player(setup.player_id)

        from ai_rpg_world.application.trace import TraceEventKind

        note_events = [e for e in recorder.events if e.kind == TraceEventKind.NOTE]
        consolidation_events = [
            e
            for e in recorder.events
            if e.kind == TraceEventKind.BELIEF_CONSOLIDATION
        ]
        assert len(note_events) == 1
        assert note_events[0].payload["batch_evidence_ids"] == ["e1"]
        assert consolidation_events == []
