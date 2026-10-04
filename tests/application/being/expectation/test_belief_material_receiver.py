"""確定した予期の出来事を、根拠の信念への支持・反証の材料として証拠バッファに積む挙動を保証する。"""

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
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
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
        "grounds": ExpectationGrounds(beliefs=("belief-tide",), episodes=("ep-shore",)),
    }
    fields.update(overrides)
    return ExpectationSettled(**fields)


class _Harness:
    def __init__(self, *, max_what_happened_chars: int = 1000) -> None:
        self.buffer = InMemoryBeliefEvidenceBufferStore()
        self.recorder = RecordingTraceRecorder()
        self.receiver = ExpectationBeliefMaterialReceiver(
            self.buffer,
            now_provider=lambda: NOW,
            trace_recorder_provider=lambda: self.recorder,
            max_what_happened_chars=max_what_happened_chars,
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
    """当否の確定が、根拠の信念へ向けた支持・反証の材料になる挙動を保証する。"""

    def test_settled_hit_supports_grounding_beliefs(self) -> None:
        """当たったで確定した予期は、根拠の信念を指す CONFIRMATION の材料として 1 件積まれる。"""
        harness = _Harness()

        harness.receive(_settled(outcome=Outcome.HIT, grounds=ExpectationGrounds(beliefs=("b-1", "b-2"))))

        (material,) = harness.materials()
        assert material.source_kind is BeliefEvidenceSourceKind.CONFIRMATION
        assert material.in_context_belief_ids == ("b-1", "b-2")
        assert material.text == "たぶんと思っていた予期「干潟で貝が採れる」は当たった。"
        assert material.salience == BELIEF_EVIDENCE_SALIENCE_LOW

    def test_settled_miss_contradicts_grounding_beliefs(self) -> None:
        """外れたで確定した予期は、根拠の信念を指す PREDICTION_ERROR の材料として 1 件積まれる。"""
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

    def test_settled_miss_without_grounding_beliefs_is_still_material(self) -> None:
        """根拠の信念が無くても、外れの確定は新しく学ぶ材料として積まれ、指す信念は空になる。"""
        harness = _Harness()

        harness.receive(_settled(grounds=ExpectationGrounds()))

        (material,) = harness.materials()
        assert material.in_context_belief_ids == ()

    def test_settled_hit_without_grounding_beliefs_is_not_material(self) -> None:
        """根拠の信念が無いときの当たりは、支える相手が無いので材料にせず、理由を trace に残す。"""
        harness = _Harness()

        harness.receive(_settled(outcome=Outcome.HIT, grounds=ExpectationGrounds()))

        assert harness.materials() == []
        (trace,) = harness.traces()
        assert trace["result"] == "skipped"
        assert trace["skipped_reason"] == "no_grounding_beliefs"


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
            "what_happened_lines": 0,
            "what_happened_truncated": False,
            "what_happened_total_lines": 0,
        }


class TestMissCarriesWhatHappened:
    """外れの材料に、予期を書いてから確定するまでに実際に起きたことが付く挙動を保証する (#1509)。"""

    def test_miss_material_carries_what_happened(self) -> None:
        """外れで確定した出来事が運ぶ時系列は、材料の what_happened に同じ並びで付き、件数が trace に残る。"""
        harness = _Harness()
        lines = ("リオ: 流木を拾う → もう拾ってしまった", "ノア「波が運んでくる」")

        harness.receive(_settled(what_happened=lines))

        (material,) = harness.materials()
        assert material.what_happened == lines
        (trace,) = harness.traces()
        assert (trace["what_happened_lines"], trace["what_happened_truncated"]) == (2, False)

    def test_hit_material_carries_no_what_happened(self) -> None:
        """当たりの材料には、出来事が時系列を運んでいても付けない。当たりに時系列を付けるのは対象外。"""
        harness = _Harness()

        harness.receive(
            _settled(
                outcome=Outcome.HIT,
                grounds=ExpectationGrounds(beliefs=("b-1",)),
                what_happened=("流木を拾えた",),
            )
        )

        (material,) = harness.materials()
        assert material.what_happened == ()

    def test_what_happened_over_limit_keeps_earliest_lines_and_traces_truncation(self) -> None:
        """時系列の文字数が上限を超えると、先頭から上限に収まる行までを残し、切り詰めたことを trace に残す。"""
        harness = _Harness(max_what_happened_chars=10)

        harness.receive(_settled(what_happened=("あいうえお", "かきくけ", "さしすせそ")))

        (material,) = harness.materials()
        assert material.what_happened == ("あいうえお", "かきくけ")
        (trace,) = harness.traces()
        assert (trace["what_happened_lines"], trace["what_happened_truncated"]) == (2, True)
        assert trace["what_happened_total_lines"] == 3

    def test_what_happened_exactly_at_limit_is_kept_whole(self) -> None:
        """時系列の文字数の合計がちょうど上限のときは、切り詰めずにすべての行を残す。"""
        harness = _Harness(max_what_happened_chars=9)

        harness.receive(_settled(what_happened=("あいうえお", "かきくけ")))

        (material,) = harness.materials()
        assert material.what_happened == ("あいうえお", "かきくけ")
        assert harness.traces()[0]["what_happened_truncated"] is False

    def test_first_line_over_limit_is_cut_to_limit(self) -> None:
        """先頭の 1 行だけで上限を超えるときは、その行を上限の文字数で切って 1 行だけ残す。"""
        harness = _Harness(max_what_happened_chars=3)

        harness.receive(_settled(what_happened=("あいうえお", "かき")))

        (material,) = harness.materials()
        assert material.what_happened == ("あいう",)
        assert harness.traces()[0]["what_happened_truncated"] is True

    def test_first_line_cut_to_blank_is_dropped(self) -> None:
        """先頭の行を上限で切ると空白だけになるときは、その行を残さず、材料は時系列を持たない。"""
        harness = _Harness(max_what_happened_chars=2)

        harness.receive(_settled(what_happened=("   あいう",)))

        (material,) = harness.materials()
        assert material.what_happened == ()
        assert harness.traces()[0]["what_happened_truncated"] is True

    @pytest.mark.parametrize("limit", [0, -1, True])
    def test_non_positive_limit_is_rejected(self, limit: object) -> None:
        """時系列の上限に 1 未満や真偽値を渡すと、受け取る側を作らずに止める。"""
        with pytest.raises((TypeError, ValueError)):
            ExpectationBeliefMaterialReceiver(
                InMemoryBeliefEvidenceBufferStore(),
                now_provider=lambda: NOW,
                trace_recorder_provider=lambda: None,
                max_what_happened_chars=limit,  # type: ignore[arg-type]
            )
