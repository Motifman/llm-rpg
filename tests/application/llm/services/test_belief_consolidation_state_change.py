"""信念を固める処理が観測のターン数を扱い、状態の変わり方を学ぶ挙動を保証する (#1452)。

「浜の枯れ葉は採り尽くされている」と信じたあとで、浜に枯れ葉が戻っているのを
見たら、状態の信念を置き換えて「浜の枯れ葉は時間がたつと戻る」を作れるようにする。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest
from tests.memory_turn_helpers import FixedMemoryTurnReader

from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
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
    SEMANTIC_MEMORY_STATUS_SUPERSEDED,
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_BEING = BeingId("being_w1_p7")
_PLAYER = PlayerId(7)
_DEPLETED = "浜の枯れ葉は採り尽くされている"
_REGROWS = "浜の枯れ葉は時間がたつと戻る"


class _FakePort(IBeliefConsolidationCompletionPort):
    def __init__(self, outcome: dict[str, Any]) -> None:
        self.outcome = outcome
        self.calls: list[list[dict[str, Any]]] = []

    def complete_belief_consolidation_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.calls.append(messages)
        return self.outcome


class _Recorder:
    def __init__(self) -> None:
        self._inner = NullTraceRecorder()
        self.events: list[Any] = []

    def record(self, kind: Any, **kw: Any) -> Any:
        ev = self._inner.record(kind, **kw)
        self.events.append(ev)
        return ev

    def close(self) -> None:
        self._inner.close()


@dataclass
class _Setup:
    coordinator: BeliefConsolidationCoordinator
    evidence_buffer: InMemoryBeliefEvidenceBufferStore
    semantic_store: InMemorySemanticMemoryStore
    port: _FakePort
    recorder: _Recorder


def _setup(
    decisions: list[dict[str, Any]],
    *,
    current_turn: int = 40,
) -> _Setup:
    evidence_buffer = InMemoryBeliefEvidenceBufferStore()
    semantic_store = InMemorySemanticMemoryStore()
    port = _FakePort({"decisions": decisions})
    recorder = _Recorder()
    coordinator = BeliefConsolidationCoordinator(
        evidence_buffer_store=evidence_buffer,
        semantic_store=semantic_store,
        completion=port,
        memory_turn_reader=FixedMemoryTurnReader(current_turn),
        trace_recorder_provider=lambda: recorder,
    )
    return _Setup(coordinator, evidence_buffer, semantic_store, port, recorder)


def _evidence(
    evidence_id: str,
    *,
    observed_turn: int,
    text: str = "浜に枯れ葉が落ちていた",
    cue_signature: str = "tool:explore|spot:浜辺",
    source_kind: BeliefEvidenceSourceKind = BeliefEvidenceSourceKind.PREDICTION_ERROR,
) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=source_kind,
        episode_ids=(f"ep-{evidence_id}",),
        cue_signature=cue_signature,
        text=text,
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        observed_turn=observed_turn,
    )


def _belief(
    *,
    entry_id: str = "sem-depleted",
    text: str = _DEPLETED,
    last_observed_turn: int | None = 12,
    support: tuple[str, ...] = ("e-old-1", "e-old-2"),
    importance: int = 6,
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=7,
        being_id=_BEING,
        text=text,
        evidence_episode_ids=("ep-old",),
        confidence=0.6,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        importance_score=importance,
        tags=("浜辺", "explore"),
        belief_id=entry_id,
        support_evidence_ids=support,
        last_observed_turn=last_observed_turn,
    )


def _user_payload(port: _FakePort) -> dict[str, Any]:
    content = port.calls[-1][1]["content"]
    return json.loads(content[content.index("{") :])


def _explain_change(**overrides: Any) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "action": "explain_change",
        "belief_id": "sem-depleted",
        "text": _REGROWS,
        "importance": 7,
        "tags": ["浜辺"],
        "evidence_ids": ["e-now"],
    }
    decision.update(overrides)
    return decision


def _active(store: InMemorySemanticMemoryStore) -> list[SemanticMemoryEntry]:
    return [
        e for e in store.list_for_being(_BEING) if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
    ]


class TestObservedTurnsInConsolidationInput:
    """固める LLM に渡す材料に、信念と出来事の観測のターン数が並ぶことを保証する。"""

    def test_refuted_belief_and_refuting_evidence_show_their_observed_turns(self) -> None:
        """turn 12 に見た状態の信念と、turn 40 に見た反する出来事が、それぞれ last_observed_turn=12 と observed_turn=40 として同じ材料に並ぶ。"""
        s = _setup([])
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=12))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        payload = _user_payload(s.port)
        assert payload["shortlist"][0]["belief_id"] == "sem-depleted"
        assert payload["shortlist"][0]["last_observed_turn"] == 12
        assert payload["evidence"][0]["observed_turn"] == 40

    def test_current_turn_is_given_with_the_material(self) -> None:
        """いまの記憶のターン数 41 が current_turn として材料に載る。"""
        s = _setup([], current_turn=41)
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        assert _user_payload(s.port)["current_turn"] == 41

    def test_belief_without_observed_turn_is_shown_as_null(self) -> None:
        """観測から作られていない信念は last_observed_turn を null として載せ、キーを省かない。"""
        s = _setup([])
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=None))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        assert _user_payload(s.port)["shortlist"][0]["last_observed_turn"] is None

    def test_system_prompt_offers_explain_change(self) -> None:
        """固める LLM の指示に、変わり方を説明する信念を作る選択肢 explain_change と、その出力の形が載る。"""
        s = _setup([])
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        system = s.port.calls[-1][0]["content"]
        assert "explain_change" in system
        assert '{"action": "explain_change", "belief_id"' in system
        assert "observed_turn" in system
        assert "last_observed_turn" in system


class TestBeliefObservedTurnOnCreateAndStrengthen:
    """作る・強めるで、信念の last_observed_turn が支える観測の最新のターンになることを保証する。"""

    def test_create_takes_latest_observed_turn_of_founding_evidence(self) -> None:
        """turn 3 と turn 9 の証拠から作った信念の last_observed_turn は 9。"""
        s = _setup(
            [{"action": "create", "text": _DEPLETED, "evidence_ids": ["e1", "e2"]}]
        )
        s.evidence_buffer.append_by_being(_BEING, _evidence("e1", observed_turn=3))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e2", observed_turn=9))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [created] = _active(s.semantic_store)
        assert created.last_observed_turn == 9

    def test_strengthen_moves_last_observed_turn_forward(self) -> None:
        """turn 12 までの観測で支えられた信念を turn 20 の証拠で強めると、last_observed_turn は 20 になる。"""
        s = _setup(
            [{"action": "strengthen", "belief_id": "sem-depleted", "evidence_ids": ["e1"]}]
        )
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=12))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e1", observed_turn=20))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [strengthened] = _active(s.semantic_store)
        assert strengthened.last_observed_turn == 20

    def test_strengthen_with_older_evidence_keeps_latest_turn(self) -> None:
        """turn 12 までの観測で支えられた信念を turn 5 の証拠で強めても、last_observed_turn は 12 のまま戻らない。"""
        s = _setup(
            [{"action": "strengthen", "belief_id": "sem-depleted", "evidence_ids": ["e1"]}]
        )
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=12))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e1", observed_turn=5))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [strengthened] = _active(s.semantic_store)
        assert strengthened.last_observed_turn == 12

    def test_contradict_does_not_move_last_observed_turn(self) -> None:
        """反する観測は信念を支えないので、turn 40 の証拠で否定しても last_observed_turn は 12 のまま。"""
        s = _setup(
            [{"action": "contradict", "belief_id": "sem-depleted", "evidence_ids": ["e1"]}]
        )
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=12))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e1", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [contradicted] = _active(s.semantic_store)
        assert contradicted.last_observed_turn == 12

    def test_revise_keeps_last_observed_turn(self) -> None:
        """言い直しは観測を足さないので、改めた信念は元の last_observed_turn 12 を引き継ぐ。"""
        s = _setup(
            [
                {
                    "action": "revise",
                    "belief_id": "sem-depleted",
                    "text": "浜の枯れ葉は採り尽くされていることが多い",
                    "reason": "言い直し",
                }
            ]
        )
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=12))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e1", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [revised] = _active(s.semantic_store)
        assert revised.last_observed_turn == 12


class TestExplainChange:
    """「変わり方を説明する信念を作る」を選んだとき、状態の信念が新しい信念に置き換わることを保証する。"""

    def test_creates_change_belief_and_supersedes_state_belief(self) -> None:
        """explain_change を適用すると、変わり方の信念が active で作られ、反証された状態の信念は superseded になり、新しい信念の supersedes が状態の信念の entry_id を指す。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        entries = {e.text: e for e in s.semantic_store.list_for_being(_BEING)}
        assert entries[_DEPLETED].status == SEMANTIC_MEMORY_STATUS_SUPERSEDED
        change = entries[_REGROWS]
        assert change.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        assert change.supersedes == "sem-depleted"

    def test_change_belief_is_a_new_belief_lineage(self) -> None:
        """変わり方の信念は状態の信念の言い直しではないので、別の belief_id を持つ。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [change] = _active(s.semantic_store)
        assert change.belief_id != "sem-depleted"
        assert change.belief_id == change.entry_id

    def test_change_belief_is_supported_by_both_observations(self) -> None:
        """変わり方の信念は、前の状態を支えた観測と、食い違った今の観測の両方に支えられ、last_observed_turn は今の観測の 40 になる。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief(support=("e-old-1", "e-old-2")))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [change] = _active(s.semantic_store)
        assert set(change.support_evidence_ids) == {"e-old-1", "e-old-2", "e-now"}
        assert change.contradict_evidence_ids == ()
        assert change.last_observed_turn == 40

    def test_change_belief_never_moves_turn_back(self) -> None:
        """状態の信念が turn 50 まで支えられ、食い違った観測が turn 40 なら、変わり方の信念の last_observed_turn は 50 のまま戻らない。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=50))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [change] = _active(s.semantic_store)
        assert change.last_observed_turn == 50

    def test_change_belief_keeps_text_importance_and_tags_from_decision(self) -> None:
        """変わり方の信念は、LLM が書いた文と importance と tags を持つ。"""
        s = _setup([_explain_change(importance=8, tags=["枯れ葉"])])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [change] = _active(s.semantic_store)
        assert change.text == _REGROWS
        assert change.importance_score == 8
        assert "枯れ葉" in change.tags

    def test_superseded_state_belief_is_no_longer_active(self) -> None:
        """置き換えられた状態の信念は active でなくなり、active な信念は変わり方の信念だけになる。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        active = [
            e.text
            for e in s.semantic_store.list_for_being(_BEING)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]
        assert active == [_REGROWS]

    def test_superseded_state_belief_leaves_the_next_shortlist(self) -> None:
        """置き換えたあとの次の固めでは、状態の信念は候補に出ず、変わり方の信念が出る。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))
        s.coordinator.flush_player(_PLAYER, _BEING)
        s.port.outcome = {"decisions": []}
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-later", observed_turn=50))

        s.coordinator.flush_player(_PLAYER, _BEING)

        assert [b["text"] for b in _user_payload(s.port)["shortlist"]] == [_REGROWS]

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"belief_id": None}, "explain_change_missing_belief_id"),
            ({"belief_id": "sem-unknown"}, "explain_change_belief_not_found"),
            ({"text": "  "}, "explain_change_empty_text"),
            ({"evidence_ids": ["e-unknown"]}, "explain_change_no_evidence"),
            ({"evidence_ids": None}, "explain_change_no_evidence"),
        ],
    )
    def test_unusable_decision_is_skipped_and_state_belief_stays(
        self, overrides: dict[str, Any], reason: str
    ) -> None:
        """置き換える信念・文・食い違った証拠のどれかが欠けた explain_change は、理由つきで見送られ、状態の信念は active のまま残る。"""
        decision = _explain_change(**overrides)
        decision = {k: v for k, v in decision.items() if v is not None}
        s = _setup([decision])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        assert [e.text for e in _active(s.semantic_store)] == [_DEPLETED]
        [trace] = [e for e in s.recorder.events if e.kind == TraceEventKind.BELIEF_CONSOLIDATION]
        assert [d["reason"] for d in trace.payload["skipped_decisions"]] == [reason]


class TestConsolidationTraceShowsTurnsAndActions:
    """信念を固める呼び出しの trace に、渡した観測のターン数と選ばれた操作が残ることを保証する。"""

    def test_trace_has_observed_turns_given_to_llm(self) -> None:
        """trace に、いまのターン、証拠ごとの observed_turn、候補の信念ごとの last_observed_turn が残る。"""
        s = _setup([_explain_change()], current_turn=41)
        s.semantic_store.add_by_being(_BEING, _belief(last_observed_turn=12))
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [trace] = [e for e in s.recorder.events if e.kind == TraceEventKind.BELIEF_CONSOLIDATION]
        assert trace.payload["current_turn"] == 41
        assert trace.payload["evidence_observed_turns"] == {"e-now": 40}
        assert trace.payload["shortlist_last_observed_turns"] == {"sem-depleted": 12}

    def test_trace_decision_records_which_belief_was_replaced_by_which(self) -> None:
        """適用した explain_change の decision に、作った変わり方の信念の belief_id が足される。"""
        s = _setup([_explain_change()])
        s.semantic_store.add_by_being(_BEING, _belief())
        s.evidence_buffer.append_by_being(_BEING, _evidence("e-now", observed_turn=40))

        s.coordinator.flush_player(_PLAYER, _BEING)

        [trace] = [e for e in s.recorder.events if e.kind == TraceEventKind.BELIEF_CONSOLIDATION]
        [decision] = trace.payload["decisions"]
        [change] = _active(s.semantic_store)
        assert decision["action"] == "explain_change"
        assert decision["belief_id"] == "sem-depleted"
        assert decision["change_belief_id"] == change.belief_id
