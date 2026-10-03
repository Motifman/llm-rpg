"""信念を固める LLM の「作る」を、作る直前の判断で置き換える仕様 (#1453)。

判定そのものは ``BeliefCreateGate`` の試験が見る。ここでは判定の結果が
belief journal と trace にどう反映されるかを見る。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
    BeliefConsolidationCoordinator,
)
from ai_rpg_world.application.llm.services.belief_create_gate import (
    NO_SAME_MEANING,
    SAME_MEANING_QUESTION,
    SHAPE_CURRENT_SITUATION,
    SHAPE_QUESTION,
    BeliefCreateGate,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CharBigramBm25Narrower,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SEMANTIC_MEMORY_STATUS_INACTIVE,
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PLAYER = PlayerId(7)
_BEING = BeingId("being_w1_p7")
_EXISTING_TEXT = "腐った貝は食べると毒になる"
_NEW_TEXT = "腐った貝を食べると毒に当たる"


class _Completion(IBeliefConsolidationCompletionPort):
    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = decisions

    def complete_belief_consolidation_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {"decisions": self.decisions}


class _Judge(ITypedJudgmentPort):
    def __init__(
        self,
        answers: Mapping[str, str] | None = None,
        *,
        raises: BaseException | None = None,
    ) -> None:
        self.answers = dict(answers or {})
        self.raises = raises
        self.option_sets: list[list[str]] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        if self.raises is not None:
            raise self.raises
        out = {}
        for name, question in questions.items():
            assert isinstance(question, ChoiceQuestion)
            if name == SAME_MEANING_QUESTION:
                self.option_sets.append(list(question.options))
            value = self.answers.get(name, next(iter(question.options)))
            out[name] = JudgmentResult(
                value=value,
                probabilities={value: 0.9},
                confidence=0.9,
                source=JudgmentSource.JEV,
                latency_ms=5.0,
            )
        return out


class _Recorder:
    def __init__(self) -> None:
        self._inner = NullTraceRecorder()
        self.events: list = []

    def record(self, kind, **kw):
        event = self._inner.record(kind, **kw)
        self.events.append(event)
        return event

    def close(self) -> None:
        self._inner.close()

    def of(self, kind: str) -> list:
        return [e for e in self.events if e.kind == kind]


def _evidence(evidence_id: str) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
        episode_ids=("ep-1",),
        cue_signature="tool:interact",
        text="腐った貝を食べて毒に当たった",
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


def _belief(entry_id: str, text: str, *, status: str = SEMANTIC_MEMORY_STATUS_ACTIVE):
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=7,
        being_id=_BEING,
        text=text,
        evidence_episode_ids=("ep-0",),
        confidence=0.5,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        tags=(),
        belief_id=entry_id,
        status=status,
        support_evidence_ids=("old-1",),
    )


def _flush(
    decisions: list[dict[str, Any]],
    judge: ITypedJudgmentPort | None,
    *,
    existing: tuple[SemanticMemoryEntry, ...] = (),
    buffer: InMemoryBeliefEvidenceBufferStore | None = None,
) -> tuple[InMemorySemanticMemoryStore, _Recorder]:
    buffer = buffer if buffer is not None else InMemoryBeliefEvidenceBufferStore()
    store = InMemorySemanticMemoryStore()
    for entry in existing:
        store.add_by_being(_BEING, entry)
    buffer.append_by_being(_BEING, _evidence("ev-1"))
    recorder = _Recorder()
    gate = (
        BeliefCreateGate(
            judgment_port=judge,
            narrower=CharBigramBm25Narrower(),
            top_k=3,
            min_confidence=0.6,
        )
        if judge is not None
        else None
    )
    coordinator = BeliefConsolidationCoordinator(
        evidence_buffer_store=buffer,
        semantic_store=store,
        completion=_Completion(decisions),
        trace_recorder_provider=lambda: recorder,
        create_gate=gate,
    )
    coordinator.flush_player(_PLAYER, _BEING)
    return store, recorder


def _create(text: str = _NEW_TEXT) -> dict[str, Any]:
    return {"action": "create", "text": text, "evidence_ids": ["ev-1"]}


def _active(store: InMemorySemanticMemoryStore) -> list[SemanticMemoryEntry]:
    return [
        e for e in store.list_for_being(_BEING) if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
    ]


class TestTheGateReplacesCreate:
    """作る前の判断で、作る / 強める / 作らないが journal に反映されることを保証する。"""

    def test_a_current_situation_is_not_written_and_is_skipped_with_a_reason(self) -> None:
        """形がいまの状況なら信念を作らず、decision は理由つきで skipped に入る。
        証拠は discard と同じく batch ごと buffer から消え、次周期に問い直さない。"""
        buffer = InMemoryBeliefEvidenceBufferStore()
        store, recorder = _flush(
            [_create("ノアとリオは干潟に向かっている")],
            _Judge({SHAPE_QUESTION: SHAPE_CURRENT_SITUATION}),
            buffer=buffer,
        )

        assert _active(store) == []
        assert buffer.list_all_by_being(_BEING) == []
        consolidation = recorder.of(TraceEventKind.BELIEF_CONSOLIDATION)[0].payload
        assert consolidation["decisions"] == []
        assert consolidation["skipped_decisions"][0]["reason"] == (
            "create_current_situation"
        )

    def test_a_same_meaning_belief_receives_the_evidence_instead(self) -> None:
        """同じ意味の既存の信念が選ばれたら新しい信念は作らず、証拠はその信念に積まれる。"""
        store, _ = _flush(
            [_create()],
            _Judge({SAME_MEANING_QUESTION: _EXISTING_TEXT}),
            existing=(_belief("sem-shell", _EXISTING_TEXT),),
        )

        active = _active(store)
        assert [e.belief_id for e in active] == ["sem-shell"]
        assert set(active[0].support_evidence_ids) == {"old-1", "ev-1"}
        assert active[0].text == _EXISTING_TEXT

    def test_a_create_without_evidence_ids_strengthens_with_the_batch(self) -> None:
        """evidence_ids を省いた create を強めるに置き換えたら、create と同じく batch の
        証拠をその信念に積む。"""
        store, _ = _flush(
            [{"action": "create", "text": _NEW_TEXT}],
            _Judge({SAME_MEANING_QUESTION: _EXISTING_TEXT}),
            existing=(_belief("sem-shell", _EXISTING_TEXT),),
        )

        assert set(_active(store)[0].support_evidence_ids) == {"old-1", "ev-1"}

    def test_an_empty_create_does_not_ask(self) -> None:
        """文の無い create は gate に問わず、従来どおり create_empty_text で skip する。"""
        judge = _Judge(raises=AssertionError("must not be asked"))

        store, recorder = _flush([_create("  ")], judge)

        assert _active(store) == []
        assert recorder.of(TraceEventKind.TYPED_JUDGMENT) == []
        skipped = recorder.of(TraceEventKind.BELIEF_CONSOLIDATION)[0].payload[
            "skipped_decisions"
        ]
        assert skipped[0]["reason"] == "create_empty_text"

    def test_the_applied_decision_shows_it_was_replaced(self) -> None:
        """強めるに置き換えた decision は、元の create と置き換え先が trace で分かる。"""
        _, recorder = _flush(
            [_create()],
            _Judge({SAME_MEANING_QUESTION: _EXISTING_TEXT}),
            existing=(_belief("sem-shell", _EXISTING_TEXT),),
        )

        applied = recorder.of(TraceEventKind.BELIEF_CONSOLIDATION)[0].payload[
            "decisions"
        ]
        assert applied[0]["action"] == "create"
        assert applied[0]["create_gate_outcome"] == "strengthen"
        assert applied[0]["strengthened_belief_id"] == "sem-shell"

    def test_no_same_meaning_creates_a_new_belief(self) -> None:
        """同じ意味が該当なしなら新しい信念が作られ、decision に縮退の理由は付かない。"""
        store, recorder = _flush(
            [_create()],
            _Judge({SAME_MEANING_QUESTION: NO_SAME_MEANING}),
            existing=(_belief("sem-shell", _EXISTING_TEXT),),
        )

        assert sorted(e.text for e in _active(store)) == sorted(
            [_EXISTING_TEXT, _NEW_TEXT]
        )
        applied = recorder.of(TraceEventKind.BELIEF_CONSOLIDATION)[0].payload[
            "decisions"
        ]
        assert applied[0]["create_gate_outcome"] == "create"
        assert "create_gate_unavailable_reason" not in applied[0]

    def test_without_a_gate_create_is_unchanged(self) -> None:
        """gate を渡さなければ、同じ文の信念があっても従来どおり作る。"""
        store, recorder = _flush(
            [_create()], None, existing=(_belief("sem-shell", _EXISTING_TEXT),)
        )

        assert len(_active(store)) == 2
        assert recorder.of(TraceEventKind.TYPED_JUDGMENT) == []

    def test_an_unavailable_judgment_still_creates(self) -> None:
        """Jev が例外を投げたら作るを通し、新しい信念が作られる。"""
        store, recorder = _flush(
            [_create()],
            _Judge(raises=TypedJudgmentUnavailableException("timeout")),
            existing=(_belief("sem-shell", _EXISTING_TEXT),),
        )

        assert len(_active(store)) == 2
        applied = recorder.of(TraceEventKind.BELIEF_CONSOLIDATION)[0].payload[
            "decisions"
        ]
        assert applied[0]["create_gate_unavailable_reason"] == (
            "TYPED_JUDGMENT_UNAVAILABLE"
        )
        gate_trace = recorder.of(TraceEventKind.TYPED_JUDGMENT)[0].payload
        assert gate_trace["outcome"] == "create"
        assert gate_trace["unavailable_reason"] == "TYPED_JUDGMENT_UNAVAILABLE"


class TestTheCandidatesComeFromActiveBeliefs:
    """候補に並ぶ既存の信念の範囲を保証する。"""

    def test_inactive_beliefs_are_not_candidates(self) -> None:
        """反証で inactive になった信念は候補に並ばない。"""
        judge = _Judge()

        _flush(
            [_create()],
            judge,
            existing=(
                _belief("sem-dead", _EXISTING_TEXT, status=SEMANTIC_MEMORY_STATUS_INACTIVE),
            ),
        )

        assert judge.option_sets == []

    def test_a_belief_created_earlier_in_the_flush_is_a_candidate(self) -> None:
        """同じ flush で先に作った信念は、後の create の候補に並ぶ。"""
        judge = _Judge()

        _flush([_create(_EXISTING_TEXT), _create(_NEW_TEXT)], judge)

        assert judge.option_sets == [[NO_SAME_MEANING, _EXISTING_TEXT]]


class TestTheJudgmentIsTraced:
    """作る前の問いごとに trace が 1 件残ることを保証する。"""

    def test_each_review_is_recorded_with_the_being_and_question(self) -> None:
        """TYPED_JUDGMENT に being_id、問いの名前、候補、答え、結果が載る。"""
        _, recorder = _flush(
            [_create()],
            _Judge({SAME_MEANING_QUESTION: _EXISTING_TEXT}),
            existing=(_belief("sem-shell", _EXISTING_TEXT),),
        )

        events = recorder.of(TraceEventKind.TYPED_JUDGMENT)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["being_id"] == _BEING.value
        assert payload["question"] == "belief_create_gate"
        assert payload["candidates"][0]["key"] == "sem-shell"
        assert payload["same_meaning"] == _EXISTING_TEXT
        assert payload["outcome"] == "strengthen"
        assert payload["target_key"] == "sem-shell"
