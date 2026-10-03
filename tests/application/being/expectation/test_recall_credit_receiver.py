"""確定した予期の当否を、それを持ったときに思い出していたエピソードへ返す挙動を保証する。

当たったなら役に立った回数を 1 増やし、外れたなら想起の記録にずれを書き添える。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tests.application.being.expectation.support import RecordingTraceRecorder

from ai_rpg_world.application.being.expectation.recall_credit import (
    ExpectationRecallCreditReceiver,
)
from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
    InMemoryEpisodicRecallSuccessStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationExpired,
    ExpectationSettled,
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

RIO = BeingId("being-rio")
EVENT_ID = ExpectationEventId("exp-1@5")


def _settled(**overrides: Any) -> ExpectationSettled:
    fields: dict[str, Any] = {
        "expectation_id": ExpectationId("exp-1"),
        "holder": RIO,
        "turn": 5,
        "content": "干潟で貝が採れる",
        "outcome": Outcome.HIT,
        "likelihood": Likelihood.PROBABLY,
        "beliefs_in_mind": (),
        "episodes_in_mind": ("ep-shore", "ep-tide"),
    }
    fields.update(overrides)
    return ExpectationSettled(**fields)


def _recall(recall_id: str, episode_id: str) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=1,
        episode_id=episode_id,
        recalled_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        source_axes=("temporal",),
        current_state_snapshot="干潟",
        recent_events_snapshot="潮が引いた",
        persona_snapshot="リオ",
        situation_cues=(),
        turn_index=1,
    )


class _Harness:
    def __init__(self) -> None:
        self.success = InMemoryEpisodicRecallSuccessStore()
        self.recall = InMemoryEpisodicRecallBufferStore()
        self.recorder = RecordingTraceRecorder()
        self.receiver = ExpectationRecallCreditReceiver(
            success_store=self.success,
            recall_buffer_store=self.recall,
            trace_recorder_provider=lambda: self.recorder,
        )

    def stamps(self) -> dict[str, str | None]:
        return {
            o.recall_id: o.prediction_outcome_error
            for o in self.recall.list_pending_by_being(RIO)
        }

    def traces(self) -> list[dict[str, Any]]:
        return self.recorder.payloads(TraceEventKind.EXPECTATION_MATERIAL)


class TestSettledHit:
    """当たったで確定したとき、思い出していたエピソードの役に立った回数が増える挙動を保証する。"""

    def test_settled_hit_adds_one_to_each_episode_in_mind(self) -> None:
        """当たったで確定すると、思い出していたエピソードそれぞれの役に立った回数が 1 増え、想起には何も書かない。"""
        harness = _Harness()
        harness.recall.append_by_being(RIO, _recall("r-1", "ep-shore"))

        harness.receiver.receive(EVENT_ID, _settled())

        assert harness.success.list_all_by_being(RIO) == {"ep-shore": 1, "ep-tide": 1}
        assert harness.stamps() == {"r-1": None}

    def test_same_event_id_twice_adds_one_only(self) -> None:
        """同じ出来事の ID を二度受け取っても、役に立った回数は 1 回分しか増えない。"""
        harness = _Harness()
        harness.receiver.receive(EVENT_ID, _settled())

        harness.receiver.receive(EVENT_ID, _settled())

        assert harness.success.get_hit_count_by_being(RIO, "ep-shore") == 1
        assert [t["result"] for t in harness.traces()] == ["appended", "already_received"]

    def test_hit_trace_names_episodes(self) -> None:
        """当たりの trace に、予期と回数を増やしたエピソードが残る。"""
        harness = _Harness()

        harness.receiver.receive(EVENT_ID, _settled())

        (trace,) = harness.traces()
        assert trace == {
            "being_id": "being-rio",
            "event_id": "exp-1@5",
            "expectation_id": "exp-1",
            "receiver": "recall_credit",
            "outcome": "hit",
            "likelihood": "probably",
            "result": "appended",
            "credit": "hit_count",
            "episode_ids": ["ep-shore", "ep-tide"],
        }


class TestSettledMiss:
    """外れたで確定したとき、思い出していたエピソードの想起にずれを書き添える挙動を保証する。"""

    def test_settled_miss_stamps_recalls_and_keeps_hit_counts(self) -> None:
        """外れたで確定すると、思い出していたエピソードの想起にずれの文を書き、役に立った回数は増やさない。"""
        harness = _Harness()
        harness.recall.append_by_being(RIO, _recall("r-1", "ep-shore"))
        harness.recall.append_by_being(RIO, _recall("r-2", "ep-elsewhere"))

        harness.receiver.receive(EVENT_ID, _settled(outcome=Outcome.MISS))

        assert harness.stamps() == {
            "r-1": "たぶんと思っていた予期「干潟で貝が採れる」は外れた。",
            "r-2": None,
        }
        assert harness.success.list_all_by_being(RIO) == {}
        (trace,) = harness.traces()
        assert trace["credit"] == "miss_stamp"


class TestNothingToCredit:
    """返す先が無いとき、確定以外の出来事のときは何も書かない挙動を保証する。"""

    def test_no_episodes_in_mind_is_skipped_with_reason(self) -> None:
        """思い出していたエピソードが無ければ何も書かず、理由を trace に残す。"""
        harness = _Harness()

        harness.receiver.receive(EVENT_ID, _settled(episodes_in_mind=()))

        assert harness.success.list_all_by_being(RIO) == {}
        assert harness.success.list_received_event_ids_by_being(RIO) == []
        (trace,) = harness.traces()
        assert trace["result"] == "skipped"
        assert trace["skipped_reason"] == "no_episodes_in_mind"

    def test_non_settled_events_write_nothing(self) -> None:
        """暫定の外れと期限切れは、回数も想起も変えず、trace も残さない。"""
        harness = _Harness()
        harness.recall.append_by_being(RIO, _recall("r-1", "ep-shore"))

        harness.receiver.receive(
            EVENT_ID,
            ProvisionallyMissed(
                expectation_id=ExpectationId("exp-1"),
                holder=RIO,
                turn=4,
                likelihood=Likelihood.ALMOST_CERTAIN,
            ),
        )
        harness.receiver.receive(
            ExpectationEventId("exp-1@9"),
            ExpectationExpired(expectation_id=ExpectationId("exp-1"), holder=RIO, turn=9),
        )

        assert harness.success.list_all_by_being(RIO) == {}
        assert harness.stamps() == {"r-1": None}
        assert harness.traces() == []
