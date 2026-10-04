"""予期の清算 (ExpectationSettlementService) が、ターンの終わりに Jev を 1 回だけ呼び、判定を予期に渡して保存し、そのあとで出来事を配る挙動を保証する。"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)

from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventDispatcher,
    ExpectationEventReceiver,
)
from ai_rpg_world.application.being.expectation.grounds import InMindTextReader
from ai_rpg_world.application.being.expectation.settlement import (
    ExpectationSettlementService,
    TurnMaterial,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
    ExpectationSettled,
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
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

RIO = BeingId("being-rio")
QUIET = TurnMaterial()


class _Receiver(ExpectationEventReceiver):
    """受け取った出来事を残す。``failures`` 回までは例外を投げ、``on_receive`` で受け取った瞬間の保存先を覗ける。"""

    def __init__(self, failures: int = 0) -> None:
        self.events: list[ExpectationEvent] = []
        self._failures = failures
        self.on_receive: Any = None

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        if self.on_receive is not None:
            self.on_receive(event_id, event)
        if self._failures > 0:
            self._failures -= 1
            raise RuntimeError("receiver is down")
        self.events.append(event)


class _NoTexts(InMindTextReader):
    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        return None

    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        return None


class _Harness:
    def __init__(
        self,
        port: ScriptedJudgmentPort,
        *,
        max_open: int = 8,
        timeline_turns: int = 3,
        receiver_failures: int = 0,
    ) -> None:
        self.repository = InMemoryExpectationRepository()
        self.recorder = RecordingTraceRecorder()
        self.receiver = _Receiver(receiver_failures)
        self.port = port
        self.service = ExpectationSettlementService(
            self.repository,
            judgment_port=port,
            dispatcher=ExpectationEventDispatcher(
                self.repository,
                receivers=(self.receiver,),
                max_attempts=3,
                trace_recorder_provider=lambda: self.recorder,
            ),
            max_open=max_open,
            timeline_turns=timeline_turns,
            grounds_reader=_NoTexts(),
            max_grounds_questions=8,
            grounds_min_probability=0.5,
            trace_recorder_provider=lambda: self.recorder,
        )

    def form(
        self, expectation_id: str, content: str, *, due: str | None = None
    ) -> None:
        """いまのターンに予期を作って保存する。予期を積む入口 (#1441) の代わり。"""
        turn = self.repository.current_turn(RIO)
        self.repository.save(
            Expectation(
                expectation_id=ExpectationId(expectation_id),
                holder=RIO,
                content=content,
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=turn,
                expires_at_turn=turn + 10,
                due=due,
            ),
            [],
        )

    def turn(self, material: TurnMaterial = QUIET) -> Any:
        self.repository.advance_turn(RIO)
        return self.service.settle_turn(RIO, self_name="リオ", material=material)

    def status(self, expectation_id: str) -> ExpectationStatus:
        for expectation in self.repository.list_all_by_being(RIO):
            if expectation.expectation_id == ExpectationId(expectation_id):
                return expectation.snapshot().status
        raise AssertionError(expectation_id)

    def settlements(self) -> list[dict[str, Any]]:
        return self.recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)


def _contents(questions: dict[str, Any], prefix: str) -> list[str]:
    return [
        q.instructions for name, q in sorted(questions.items()) if name.startswith(prefix)
    ]


class TestOneCallPerTurn:
    """1 ターンに問う質問を 1 回の呼び出しにまとめ、問うものが無いターンは呼ばない挙動を保証する。"""

    def test_new_and_pending_expectations_are_asked_in_one_call(self) -> None:
        """このターンに書いた予期と清算待ちの予期があるターンは、形の問い・清算の問い・場面の問いを 1 回の呼び出しで問う。"""
        harness = _Harness(ScriptedJudgmentPort({}, {}))
        harness.repository.advance_turn(RIO)
        harness.form("exp-old", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        harness.repository.advance_turn(RIO)
        harness.form("exp-new", "ノアが干潟から戻る")

        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        assert len(harness.port.calls) == 2
        _, questions = harness.port.calls[1]
        assert set(questions) == {"shape_0", "check_0", "scene_changed"}
        assert isinstance(questions["shape_0"], ChoiceQuestion)
        assert "ノアが干潟から戻る" in questions["shape_0"].instructions
        assert isinstance(questions["check_0"], ChoiceQuestion)
        assert "カイが焚き火を起こす" in questions["check_0"].instructions
        assert isinstance(questions["scene_changed"], NoulQuestion)

    def test_turn_without_expectations_does_not_call_and_is_traced(self) -> None:
        """清算待ちも新しい予期も無いターンは Jev を呼ばず、呼ばなかった理由を trace に 1 件残す。"""
        harness = _Harness(ScriptedJudgmentPort())

        harness.turn()

        assert harness.port.calls == []
        (trace,) = harness.settlements()
        assert (trace["judged"], trace["skipped_reason"]) == (False, "nothing_to_judge")

    def test_check_question_explains_unmet_precondition_as_undetermined(self) -> None:
        """清算の問いの「まだ分からない」は、予期の前提や条件がまだ起きていない場合を含むと説明する。"""
        harness = _Harness(ScriptedJudgmentPort({}, {}))
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "焚き火がついた後、エイダが手記を説明する")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        _, questions = harness.port.calls[1]
        undetermined = questions["check_0"].options["undetermined"]
        assert "前提や条件がまだ起きていない" in undetermined


class TestApplyingJudgments:
    """判定を予期の集約に渡して保存し、返った出来事を配る挙動を保証する。"""

    def test_own_action_shape_is_not_asked_next_turn(self) -> None:
        """形の判定が「本人の行動」の予期は外され、次のターンの清算の問いに入らない。"""
        harness = _Harness(ScriptedJudgmentPort({"shape_0": "own_action"}, {}))
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "リオが川沿いへ出発する")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        assert harness.status("exp-1") is ExpectationStatus.DISMISSED
        assert len(harness.port.calls) == 1

    def test_two_consecutive_hits_settle_and_deliver(self) -> None:
        """2 ターン続けて当たったと判定された予期は確定し、確定の出来事が保存のあとで受け取る側に届く。"""
        harness = _Harness(
            ScriptedJudgmentPort({}, {"check_0": "hit"}, {"check_0": "hit"})
        )
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn(TurnMaterial(actions=("カイが焚き火を起こした",)))
        delivered_after_one_hit = list(harness.receiver.events)
        harness.turn()

        assert delivered_after_one_hit == []
        (settled,) = harness.receiver.events
        assert isinstance(settled, ExpectationSettled)
        assert (settled.outcome, settled.turn) == (Outcome.HIT, 3)
        assert harness.status("exp-1") is ExpectationStatus.SETTLED
        assert harness.repository.list_undelivered_by_being(RIO) == []

    def test_trace_records_state_answers_and_transitions(self) -> None:
        """Jev を呼んだターンは、渡した state、質問ごとの答えと確率、予期ごとの状態の移りを 1 件の trace に残す。"""
        harness = _Harness(ScriptedJudgmentPort({"shape_0": "true_either_way"}))
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "カイが来るか、来ないか")

        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        (trace,) = harness.settlements()
        assert trace["judged"] is True
        assert trace["state"] == harness.port.calls[0][0]
        assert trace["answers"]["shape_0"]["value"] == "true_either_way"
        assert set(trace["answers"]["shape_0"]["probabilities"]) == {
            "settleable",
            "true_either_way",
            "own_action",
            "not_an_expectation",
        }
        assert trace["transitions"] == [
            {
                "expectation_id": "exp-1",
                "step": "shape",
                "verdict": "true_either_way",
                "event": "ExpectationDismissed",
                "status_after": "dismissed",
            }
        ]


def _settle_exp1_by_two_hits(harness: _Harness) -> None:
    harness.repository.advance_turn(RIO)
    harness.form("exp-1", "カイが焚き火を起こす")
    harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
    harness.turn()
    harness.turn()


class TestDeliveryThroughSettlement:
    """清算のターンが、保存してから配り、配れなかった出来事を後のターンで配り直す挙動を保証する。"""

    def test_receiver_sees_saved_state_when_event_arrives(self) -> None:
        """確定の出来事が受け取る側に届いた時点で、予期はすでに確定として保存され、出来事も未配信として保存先にある。"""
        harness = _Harness(ScriptedJudgmentPort({}, {"check_0": "hit"}, {"check_0": "hit"}))
        seen: list[tuple[ExpectationStatus, list[str]]] = []
        harness.receiver.on_receive = lambda event_id, event: seen.append(
            (
                harness.status("exp-1"),
                [u.event_id.value for u in harness.repository.list_undelivered_by_being(RIO)],
            )
        )

        _settle_exp1_by_two_hits(harness)

        assert seen == [(ExpectationStatus.SETTLED, ["exp-1@3"])]

    def test_failed_delivery_is_retried_on_next_quiet_turn(self) -> None:
        """確定のターンに受け取る側が失敗しても清算は例外を出さずに終わり、出来事は未配信で残り、問うものが無い次のターンに配られる。"""
        harness = _Harness(
            ScriptedJudgmentPort({}, {"check_0": "hit"}, {"check_0": "hit"}),
            receiver_failures=1,
        )
        _settle_exp1_by_two_hits(harness)
        left_after_failure = len(harness.repository.list_undelivered_by_being(RIO))

        harness.turn()

        assert left_after_failure == 1
        assert [type(e).__name__ for e in harness.receiver.events] == ["ExpectationSettled"]
        assert harness.repository.list_undelivered_by_being(RIO) == []
        assert len(harness.port.calls) == 3

    def test_failed_delivery_is_retried_on_unavailable_turn(self) -> None:
        """配れなかった出来事は、Jev が答えられなかったターンにも配り直される。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                {},
                {"check_0": "hit"},
                {"check_0": "hit", "shape_0": "settleable"},
                TypedJudgmentUnavailableException("timeout"),
            ),
            receiver_failures=1,
        )
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        harness.turn()
        harness.repository.advance_turn(RIO)
        harness.form("exp-2", "ノアが戻る")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        assert harness.settlements()[-1]["skipped_reason"] == "judgment_unavailable"
        assert [type(e).__name__ for e in harness.receiver.events] == ["ExpectationSettled"]


class TestStateMaterial:
    """Jev に渡す state が、名前・清算待ちの一覧・直近の時系列だけを持ち、ID を持たない挙動を保証する。"""

    def test_timeline_keeps_only_recent_turns_and_old_expectation_stays_listed(
        self,
    ) -> None:
        """時系列は直近の上限ターン分だけを行動と発言に分けて載せ、それより前に書いた予期は書いたターンと文で一覧に残る。"""
        harness = _Harness(ScriptedJudgmentPort(), timeline_turns=2)
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "カイが焚き火を起こす", due="夕方まで")
        harness.service.settle_turn(
            RIO, self_name="リオ", material=TurnMaterial(actions=("リオが薪を拾った",))
        )

        harness.turn(TurnMaterial(speeches=("カイ「火打ち石はある」",)))
        harness.turn(TurnMaterial(actions=("ノアが干潟へ向かった",)))

        state, _ = harness.port.calls[-1]
        assert state["本人の名前"] == "リオ"
        assert state["出来事の時系列"] == [
            {"ターン": "ターン2", "行動": [], "発言": ["カイ「火打ち石はある」"]},
            {"ターン": "ターン3", "行動": ["ノアが干潟へ向かった"], "発言": []},
        ]
        assert state["清算待ちの予期"] == [
            {
                "書いたターン": "ターン1",
                "いつ頃": "夕方まで",
                "確からしさ": "たぶん",
                "予期": "カイが焚き火を起こす",
            }
        ]

    def test_state_has_no_ids_and_no_integers(self) -> None:
        """state には予期の ID も Being の ID も入らず、ターンも文で書くので整数が 1 つも入らない。"""
        harness = _Harness(ScriptedJudgmentPort())
        harness.repository.advance_turn(RIO)
        harness.form("exp-old", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        harness.repository.advance_turn(RIO)
        harness.form("exp-new", "ノアが戻る")

        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        state, questions = harness.port.calls[-1]
        dumped = json.dumps(state, ensure_ascii=False) + "".join(
            q.instructions for q in questions.values()
        )
        assert "exp-old" not in dumped and "exp-new" not in dumped
        assert "being-rio" not in dumped
        assert _integers(state) == []


def _integers(value: Any) -> list[int]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, dict):
        return [i for v in value.values() for i in _integers(v)]
    if isinstance(value, (list, tuple)):
        return [i for v in value for i in _integers(v)]
    return []


class TestCapacityAndDeadline:
    """期限と件数の上限で、問う前に予期を閉じる挙動を保証する。"""

    def test_over_capacity_expires_oldest_without_due_first(self) -> None:
        """清算待ちが上限を超えたとき、期日の無い予期のうち古いものから期限切れにし、期日のある古い予期は残して問う。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                {}, {"check_0": "undetermined", "check_1": "undetermined"}
            ),
            max_open=2,
        )
        harness.repository.advance_turn(RIO)
        harness.form("exp-due", "二日後にカイと会う", due="二日後")
        harness.form("exp-old", "ノアが戻る")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        harness.repository.advance_turn(RIO)
        harness.form("exp-mid", "雨が降る")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        assert harness.status("exp-old") is ExpectationStatus.EXPIRED
        assert harness.status("exp-due") is ExpectationStatus.OPEN
        _, questions = harness.port.calls[-1]
        asked = " ".join(_contents(questions, "check_"))
        assert "二日後にカイと会う" in asked and "雨が降る" in asked
        assert "ノアが戻る" not in asked
        over = [t for t in harness.settlements()[-1]["transitions"] if t["step"] == "over_capacity"]
        assert [t["expectation_id"] for t in over] == ["exp-old"]

    def test_over_capacity_closes_by_formed_turn_not_by_saved_order(self) -> None:
        """期日の無い予期どうしでは、保存した順ではなく書いたターンの古いものから閉じる。"""
        harness = _Harness(
            ScriptedJudgmentPort({"check_0": "undetermined", "check_1": "undetermined"}),
            max_open=1,
        )
        for turn, expectation_id in ((3, "exp-newer"), (1, "exp-older")):
            harness.repository.save(
                Expectation(
                    expectation_id=ExpectationId(expectation_id),
                    holder=RIO,
                    content=f"{expectation_id} の予期",
                    origin=ExpectationOrigin.WITH_ACTION,
                    likelihood=Likelihood.PROBABLY,
                    formed_at_turn=turn,
                    expires_at_turn=turn + 10,
                ),
                [],
            )
            harness.repository.save(
                _shaped(harness.repository, expectation_id, turn), []
            )
        for _ in range(4):
            harness.repository.advance_turn(RIO)

        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        assert harness.status("exp-older") is ExpectationStatus.EXPIRED
        assert harness.status("exp-newer") is ExpectationStatus.OPEN

    def test_overdue_expectation_is_closed_and_not_asked(self) -> None:
        """期限のターンを過ぎた予期は問う前に閉じ、清算の問いに入れない。"""
        harness = _Harness(ScriptedJudgmentPort())
        harness.repository.advance_turn(RIO)
        harness.repository.save(
            Expectation(
                expectation_id=ExpectationId("exp-1"),
                holder=RIO,
                content="カイが焚き火を起こす",
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=1,
                expires_at_turn=1,
            ),
            [],
        )
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        assert harness.status("exp-1") is ExpectationStatus.EXPIRED
        assert len(harness.port.calls) == 1


class TestUnavailableJudgment:
    """判断が得られないターンは、判定を既定値で埋めずに飛ばし、理由を trace に残す挙動を保証する。"""

    def test_exception_keeps_every_expectation_and_traces_reason(self) -> None:
        """Jev が例外を投げたターンは、どの予期の状態も変えず、縮退の理由を trace に残す。次のターンには同じ予期をもう一度問う。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                {},
                TypedJudgmentUnavailableException(
                    "timeout", error_code="TYPED_JUDGMENT_TIMEOUT"
                ),
                {},
            )
        )
        harness.repository.advance_turn(RIO)
        harness.form("exp-old", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        harness.repository.advance_turn(RIO)
        harness.form("exp-new", "ノアが戻る")
        before = [e.snapshot() for e in harness.repository.list_all_by_being(RIO)]

        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        after = [e.snapshot() for e in harness.repository.list_all_by_being(RIO)]
        harness.turn()

        assert after == before
        failed = harness.settlements()[1]
        assert failed["judged"] is False
        assert failed["skipped_reason"] == "judgment_unavailable"
        assert "TYPED_JUDGMENT_TIMEOUT" in failed["unavailable_reason"]
        assert failed["transitions"] == []
        _, retried = harness.port.calls[2]
        assert any("カイが焚き火を起こす" in q for q in _contents(retried, "check_"))

    def test_shape_unjudged_on_failure_is_asked_again_next_turn(self) -> None:
        """予期を書いたターンに Jev が例外を投げたら、次のターンにはその予期へ清算の問いではなく形の問いをもう一度出す。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                TypedJudgmentUnavailableException("timeout"), {"shape_0": "own_action"}
            )
        )
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "リオが川沿いへ出発する")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        _, questions = harness.port.calls[1]
        assert set(questions) == {"shape_0", "scene_changed"}
        assert harness.status("exp-1") is ExpectationStatus.DISMISSED

    def test_failure_after_closing_by_deadline_traces_closed_expectations(self) -> None:
        """問う前に期限で予期を閉じたあとで Jev が想定外の例外を投げると、閉じた予期と理由を trace に残し、保存済みの出来事を配ってから例外を投げ直す。"""
        harness = _Harness(ScriptedJudgmentPort({}, RuntimeError("bug")))
        harness.repository.advance_turn(RIO)
        harness.repository.save(
            Expectation(
                expectation_id=ExpectationId("exp-due"),
                holder=RIO,
                content="カイが来る",
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=1,
                expires_at_turn=1,
            ),
            [],
        )
        harness.form("exp-open", "ノアが戻る")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        with pytest.raises(RuntimeError):
            harness.turn()

        failed = harness.settlements()[-1]
        assert failed["skipped_reason"] == "settlement_failed"
        assert failed["unavailable_reason"] == "RuntimeError: bug"
        assert [t["step"] for t in failed["transitions"]] == ["overdue"]
        assert failed["state"] is not None
        assert harness.repository.list_undelivered_by_being(RIO) == []

    def test_one_unusable_answer_keeps_every_expectation(self) -> None:
        """新しい予期と清算待ちの予期を同じターンに問い、片方の答えだけが選択肢に無い値でも、どちらの予期の状態も変えない。"""
        harness = _Harness(_BrokenAnswerPort({"check_0": "certainly"}))
        harness.repository.advance_turn(RIO)
        harness.form("exp-old", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)
        harness.repository.advance_turn(RIO)
        harness.form("exp-new", "ノアが戻る")
        before = [e.snapshot() for e in harness.repository.list_all_by_being(RIO)]

        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        assert [e.snapshot() for e in harness.repository.list_all_by_being(RIO)] == before

    @pytest.mark.parametrize(
        "answers",
        [{"check_0": "certainly"}, {"scene_changed": None}, {"scene_changed": "high"}],
        ids=["unknown_option", "missing_answer", "non_numeric_scene"],
    )
    def test_unusable_answer_is_treated_as_unavailable(
        self, answers: dict[str, Any]
    ) -> None:
        """選択肢に無い答えや欠けた答えは判定として使わず、Jev の例外と同じく状態を変えずに理由を trace に残す。"""
        harness = _Harness(_BrokenAnswerPort(answers))
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "カイが焚き火を起こす")
        harness.service.settle_turn(RIO, self_name="リオ", material=QUIET)

        harness.turn()

        assert harness.status("exp-1") is ExpectationStatus.OPEN
        assert harness.settlements()[-1]["skipped_reason"] == "judgment_unavailable"


class _BrokenAnswerPort(ScriptedJudgmentPort):
    """2 回目の呼び出しだけ、迷った答えの一部を壊して返す。値が None の質問は答えから落とす。"""

    def __init__(self, broken: dict[str, Any]) -> None:
        super().__init__()
        self._broken = broken

    def judge(self, state: Any, questions: Any) -> Any:
        answers = dict(super().judge(state, questions))
        if len(self.calls) < 2:
            return answers
        for name, value in self._broken.items():
            if value is None:
                answers.pop(name)
            else:
                answers[name] = replace(answers[name], value=value)
        return answers


def _shaped(
    repository: InMemoryExpectationRepository, expectation_id: str, turn: int
) -> Expectation:
    """保存済みの予期に、清算できる形の判定を済ませて返す。"""
    (expectation,) = [
        e
        for e in repository.list_all_by_being(RIO)
        if e.expectation_id == ExpectationId(expectation_id)
    ]
    expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=turn, grounds=ExpectationGrounds())
    return expectation


class TestMissCarriesWhatHappened:
    """外れで確定した出来事が、予期を書いたターンから確定したターンまでの時系列を運ぶ挙動を保証する (#1509)。"""

    def _form_after_a_quiet_turn(self, harness: _Harness) -> None:
        harness.turn(TurnMaterial(actions=("書く前の出来事",)))
        harness.repository.advance_turn(RIO)
        harness.form("exp-1", "流木を入手できる")
        harness.service.settle_turn(
            RIO,
            self_name="リオ",
            material=TurnMaterial(actions=("リオ: 流木を拾う → もう拾ってしまった",), speeches=("カイ「流木は?」",)),
        )

    def test_settled_miss_carries_timeline_from_formed_turn_to_settled_turn(self) -> None:
        """外れで確定した出来事は、書いたターンから確定したターンまでの行動と発言を、ターン順・行動が先の並びで運び、書く前のターンの出来事は含めない。"""
        harness = _Harness(
            ScriptedJudgmentPort({}, {"check_0": "miss"}, {"check_0": "miss"}),
            timeline_turns=5,
        )
        self._form_after_a_quiet_turn(harness)

        harness.turn(TurnMaterial(actions=("浜に流木は無い",)))
        harness.turn(TurnMaterial(speeches=("ノア「波が運んでくる」",)))

        (settled,) = _settled_events(harness)
        assert settled.outcome is Outcome.MISS
        assert settled.what_happened == (
            "リオ: 流木を拾う → もう拾ってしまった",
            "カイ「流木は?」",
            "浜に流木は無い",
            "ノア「波が運んでくる」",
        )

    def test_settled_hit_carries_no_timeline(self) -> None:
        """当たりで確定した出来事は時系列を運ばない。当たりの材料に時系列を付けるのは対象外。"""
        harness = _Harness(
            ScriptedJudgmentPort({}, {"check_0": "hit"}, {"check_0": "hit"}),
            timeline_turns=5,
        )
        self._form_after_a_quiet_turn(harness)

        harness.turn(TurnMaterial(actions=("流木を拾えた",)))
        harness.turn()

        (settled,) = _settled_events(harness)
        assert settled.what_happened == ()

    def test_miss_settled_by_expiry_also_carries_timeline(self) -> None:
        """期限を過ぎて暫定の外れで確定した出来事も、書いたターンから確定したターンまでの時系列を運ぶ。"""
        harness = _Harness(ScriptedJudgmentPort({}, {"check_0": "miss"}), timeline_turns=20)
        harness.repository.advance_turn(RIO)
        harness.repository.save(
            Expectation(
                expectation_id=ExpectationId("exp-1"),
                holder=RIO,
                content="流木を入手できる",
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=1,
                expires_at_turn=2,
            ),
            [],
        )
        harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial(actions=("拾いに行く",)))
        harness.turn(TurnMaterial(actions=("流木は無い",)))

        harness.turn(TurnMaterial(actions=("期限の後",)))

        (settled,) = _settled_events(harness)
        assert settled.what_happened == ("拾いに行く", "流木は無い", "期限の後")


def _settled_events(harness: _Harness) -> list[ExpectationSettled]:
    return [e for e in harness.receiver.events if isinstance(e, ExpectationSettled)]
