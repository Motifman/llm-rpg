"""固着パス BeliefConsolidationCoordinator の検証 (U3b)。

LLM は stub (``_FakeBeliefConsolidationPort``) を使い、実際の litellm 呼び出し
は一切行わない。
"""

from __future__ import annotations

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


def _build_setup(
    *,
    outcome: dict[str, Any] | BaseException,
    turn_interval: int = 10,
    batch_size: int = 8,
    shortlist_top_k: int = 5,
    cue_signature_repeat_threshold: int = DEFAULT_CUE_SIGNATURE_REPEAT_THRESHOLD,
    contradict_inactive_threshold: float = 0.2,
    completion: Any = _UNSET,
) -> _Setup:
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    player_id = PlayerId(7)
    being_id = provisioning.ensure_attached(player_id)

    evidence_buffer = InMemoryBeliefEvidenceBufferStore()
    semantic_store = InMemorySemanticMemoryStore()
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
        being_attachment_resolver=resolver,
        default_world_id=_WORLD_ID,
    )
    return _Setup(
        coordinator=coordinator,
        evidence_buffer=evidence_buffer,
        semantic_store=semantic_store,
        port=port,
        being_id=being_id,
        player_id=player_id,
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
) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=source_kind,
        episode_ids=episode_ids,
        cue_signature=cue_signature,
        text=text,
        salience=salience,
        occurred_at=occurred_at or datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


def _belief_entry(
    *,
    entry_id: str = "sem-existing",
    belief_id: str | None = None,
    text: str = "この島の探索は空振りが多い",
    tags: tuple[str, ...] = ("explore",),
    support: tuple[str, ...] = (),
    contradict: tuple[str, ...] = (),
    status: str = SEMANTIC_MEMORY_STATUS_ACTIVE,
    created_at: datetime | None = None,
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=7,
        text=text,
        evidence_episode_ids=("ep-0",),
        confidence=compute_belief_confidence(len(support), len(contradict)),
        created_at=created_at or datetime(2026, 6, 1, tzinfo=timezone.utc),
        tags=tags,
        belief_id=belief_id or entry_id,
        status=status,
        support_evidence_ids=support,
        contradict_evidence_ids=contradict,
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

    def test_unresolved_being_is_noop(self) -> None:
        """Being 未 provision の player は silent no-op (turn を止めない)。"""
        setup = _build_setup(outcome={"decisions": []})
        unprovisioned_player = PlayerId(999)

        processed = setup.coordinator.flush_player(unprovisioned_player)

        assert processed == 0
        assert setup.port.calls == []


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
