"""確定した予期の出来事を、頭にあった信念への支持・反証の材料として証拠バッファに積む挙動を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from tests.application.being.expectation.support import RecordingTraceRecorder

from ai_rpg_world.application.being.expectation.belief_material import (
    ExpectationBeliefMaterialReceiver,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationDismissed,
    ExpectationEvent,
    ExpectationExpired,
    ExpectationSettled,
    ExpectationVoided,
    ProvisionallyMissed,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

RIO = BeingId("being-rio")
NOW = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
EVENT_ID = ExpectationEventId("exp-1@5")


def _settled(**overrides: Any) -> ExpectationSettled:
    fields: dict[str, Any] = {
        "expectation_id": ExpectationId("exp-1"),
        "holder": RIO,
        "turn": 5,
        "content": "干潟で貝が採れる",
        "outcome": Outcome.MISS,
        "likelihood": Likelihood.PROBABLY,
        "beliefs_in_mind": ("belief-tide",),
        "episodes_in_mind": ("ep-shore",),
    }
    fields.update(overrides)
    return ExpectationSettled(**fields)


class _Harness:
    def __init__(self) -> None:
        self.buffer = InMemoryBeliefEvidenceBufferStore()
        self.recorder = RecordingTraceRecorder()
        self.receiver = ExpectationBeliefMaterialReceiver(
            self.buffer,
            now_provider=lambda: NOW,
            trace_recorder_provider=lambda: self.recorder,
        )

    def receive(
        self, event: ExpectationEvent, event_id: ExpectationEventId = EVENT_ID
    ) -> None:
        self.receiver.receive(event_id, event)

    def materials(self) -> list[Any]:
        return self.buffer.list_all_by_being(RIO)

    def traces(self) -> list[dict[str, Any]]:
        return self.recorder.payloads(TraceEventKind.EXPECTATION_MATERIAL)


class TestSettledOutcomeBecomesMaterial:
    """当否の確定が、頭にあった信念へ向けた支持・反証の材料になる挙動を保証する。"""

    def test_settled_hit_supports_beliefs_in_mind(self) -> None:
        """当たったで確定した予期は、頭にあった信念を指す CONFIRMATION の材料として 1 件積まれる。"""
        harness = _Harness()

        harness.receive(_settled(outcome=Outcome.HIT, beliefs_in_mind=("b-1", "b-2")))

        (material,) = harness.materials()
        assert material.source_kind is BeliefEvidenceSourceKind.CONFIRMATION
        assert material.in_context_belief_ids == ("b-1", "b-2")
        assert material.text == "たぶんと思っていた予期「干潟で貝が採れる」は当たった。"
        assert material.salience == BELIEF_EVIDENCE_SALIENCE_LOW

    def test_settled_miss_contradicts_beliefs_in_mind(self) -> None:
        """外れたで確定した予期は、頭にあった信念を指す PREDICTION_ERROR の材料として 1 件積まれる。"""
        harness = _Harness()

        harness.receive(_settled(outcome=Outcome.MISS))

        (material,) = harness.materials()
        assert material.source_kind is BeliefEvidenceSourceKind.PREDICTION_ERROR
        assert material.in_context_belief_ids == ("belief-tide",)
        assert material.text == "たぶんと思っていた予期「干潟で貝が採れる」は外れた。"

    def test_material_is_traceable_to_expectation_and_settled_turn(self) -> None:
        """材料は予期の ID をたどれ、観測のターン数は確定したターンになり、ID は出来事の ID から決まる。"""
        harness = _Harness()

        harness.receive(_settled(turn=7))

        (material,) = harness.materials()
        assert material.episode_ids == ("exp-1",)
        assert material.observed_turn == 7
        assert material.evidence_id == "belief-evidence-exp-1@5"
        assert material.cue_signature == "expectation:miss"
        assert material.occurred_at == NOW

    def test_settled_miss_without_beliefs_in_mind_is_still_material(self) -> None:
        """頭に信念が無くても、外れの確定は新しく学ぶ材料として積まれ、指す信念は空になる。"""
        harness = _Harness()

        harness.receive(_settled(beliefs_in_mind=()))

        (material,) = harness.materials()
        assert material.in_context_belief_ids == ()

    def test_settled_hit_without_beliefs_in_mind_is_not_material(self) -> None:
        """頭に信念が無いときの当たりは、支える相手が無いので材料にせず、理由を trace に残す。"""
        harness = _Harness()

        harness.receive(_settled(outcome=Outcome.HIT, beliefs_in_mind=()))

        assert harness.materials() == []
        (trace,) = harness.traces()
        assert trace["result"] == "skipped"
        assert trace["skipped_reason"] == "no_beliefs_in_mind"


class TestLikelihoodSetsStrength:
    """本人が付けた確からしさで、外れの材料の強さが変わる挙動を保証する。"""

    def test_almost_certain_miss_is_high_salience(self) -> None:
        """ほぼ確実と思っていた予期の外れは、次の固着を待たずに扱われる強い材料になる。"""
        harness = _Harness()

        harness.receive(_settled(likelihood=Likelihood.ALMOST_CERTAIN))

        (material,) = harness.materials()
        assert material.salience == BELIEF_EVIDENCE_SALIENCE_HIGH
        assert material.text.startswith("ほぼ確実と思っていた予期")

    @pytest.mark.parametrize(
        ("likelihood", "label"),
        [
            (Likelihood.PROBABLY, "たぶん"),
            (Likelihood.EVEN, "半々"),
            (Likelihood.MAYBE, "もしかしたら"),
        ],
    )
    def test_less_certain_miss_is_low_salience_with_likelihood_in_text(
        self, likelihood: Likelihood, label: str
    ) -> None:
        """ほぼ確実より弱い予期の外れは弱い材料になり、確からしさは文に残して固着に読ませる。"""
        harness = _Harness()

        harness.receive(_settled(likelihood=likelihood))

        (material,) = harness.materials()
        assert material.salience == BELIEF_EVIDENCE_SALIENCE_LOW
        assert material.text.startswith(f"{label}と思っていた予期")

    def test_almost_certain_hit_stays_low_salience(self) -> None:
        """当たりはほぼ確実でも弱い材料のままにする。的中は繰り返してはじめて意味を持つ。"""
        harness = _Harness()

        harness.receive(
            _settled(outcome=Outcome.HIT, likelihood=Likelihood.ALMOST_CERTAIN)
        )

        (material,) = harness.materials()
        assert material.salience == BELIEF_EVIDENCE_SALIENCE_LOW


class TestOnlySettledOutcomesAreMaterial:
    """確定の判定だけが材料になり、暫定・期限切れ・外した予期は材料にならない挙動を保証する。"""

    @pytest.mark.parametrize(
        "event",
        [
            ProvisionallyMissed(
                expectation_id=ExpectationId("exp-1"),
                holder=RIO,
                turn=4,
                likelihood=Likelihood.ALMOST_CERTAIN,
            ),
            ExpectationExpired(expectation_id=ExpectationId("exp-1"), holder=RIO, turn=9),
            ExpectationDismissed(
                expectation_id=ExpectationId("exp-1"),
                holder=RIO,
                turn=2,
                shape=ShapeVerdict.TRUE_EITHER_WAY,
            ),
            ExpectationVoided(expectation_id=ExpectationId("exp-1"), holder=RIO, turn=3),
        ],
        ids=["provisional_miss", "expired", "dismissed", "voided"],
    )
    def test_non_settled_event_adds_nothing(self, event: ExpectationEvent) -> None:
        """暫定の外れ、期限切れ、形の判定で外した予期、予期になっていない予期は、材料を積まず trace も残さない。"""
        harness = _Harness()

        harness.receive(event)

        assert harness.materials() == []
        assert harness.traces() == []


class TestReceivingTwice:
    """配り直しで同じ出来事が二度届いても、材料が 1 回分しか積まれない挙動を保証する。"""

    def test_same_event_id_twice_keeps_one_material(self) -> None:
        """同じ出来事の ID を二度受け取ると、材料は 1 件のままで、2 回目は受け取り済みとして trace に残る。"""
        harness = _Harness()
        harness.receive(_settled())

        harness.receive(_settled())

        assert len(harness.materials()) == 1
        assert [t["result"] for t in harness.traces()] == ["appended", "already_received"]

    def test_redelivery_after_consolidation_drained_does_not_add_again(self) -> None:
        """固着が材料を使って取り除いたあとに配り直されても、材料を積み直さない。"""
        harness = _Harness()
        harness.receive(_settled())
        harness.buffer.remove_by_being(RIO, ["belief-evidence-exp-1@5"])

        harness.receive(_settled())

        assert harness.materials() == []


class TestTrace:
    """予期ごとに、どの信念にどの材料を積んだかを trace で読める挙動を保証する。"""

    def test_appended_material_names_beliefs_and_strength(self) -> None:
        """積んだときの trace に、予期・当否・確からしさ・材料の ID と種別と強さ・指した信念が残る。"""
        harness = _Harness()

        harness.receive(_settled(likelihood=Likelihood.ALMOST_CERTAIN))

        (trace,) = harness.traces()
        assert trace == {
            "being_id": "being-rio",
            "event_id": "exp-1@5",
            "expectation_id": "exp-1",
            "receiver": "belief_evidence",
            "outcome": "miss",
            "likelihood": "almost_certain",
            "result": "appended",
            "evidence_id": "belief-evidence-exp-1@5",
            "source_kind": "prediction_error",
            "salience": "high",
            "belief_ids": ["belief-tide"],
        }
