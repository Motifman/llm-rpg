"""ExpectationSettlementService が、次のターンの想起で残す欄を清算と同じ Jev の呼び出しで毎ターン問い、予期の判定とは分けて読む挙動を保証する (#1414)。"""

from __future__ import annotations

from typing import Any

import pytest
from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)

from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventDispatcher,
)
from ai_rpg_world.application.being.expectation.grounds import InMindTextReader
from ai_rpg_world.application.being.expectation.settlement import (
    SKIPPED_JUDGMENT_UNAVAILABLE,
    SKIPPED_NOTHING_TO_JUDGE,
    SKIPPED_SETTLEMENT_FAILED,
    ExpectationSettlementService,
    TurnMaterial,
)
from ai_rpg_world.application.being.recall.selection_store import NextTurnFieldSelections
from ai_rpg_world.application.being.recall.situation import (
    DEGRADED_ANSWER_MISSING,
    DEGRADED_JUDGMENT_UNAVAILABLE,
    DROP,
    KEEP,
    SELECTABLE_FIELDS,
    SituationField,
    field_question_name,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import Expectation
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import Likelihood
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

RIO = BeingId("being-rio")
FIELD_NAMES = {field_question_name(f) for f in SELECTABLE_FIELDS}


def _fields(keep: set[SituationField]) -> dict[str, str]:
    return {field_question_name(f): KEEP if f in keep else DROP for f in SELECTABLE_FIELDS}


class _DroppingPort(ScriptedJudgmentPort):
    """台本どおりに答えたうえで、``drop`` の問いの答えだけを返さない。"""

    def __init__(self, script: dict[str, Any], *, drop: str) -> None:
        super().__init__(script)
        self._drop = drop

    def judge(self, state: Any, questions: Any) -> Any:
        answers = dict(super().judge(state, questions))
        answers.pop(self._drop, None)
        return answers


class _NoTexts(InMindTextReader):
    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        return None

    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        return None


class _Harness:
    def __init__(self, port: ScriptedJudgmentPort, *, with_fields: bool = True) -> None:
        self.repository = InMemoryExpectationRepository()
        self.recorder = RecordingTraceRecorder()
        self.port = port
        self.selections = NextTurnFieldSelections() if with_fields else None
        self.service = ExpectationSettlementService(
            self.repository,
            judgment_port=port,
            dispatcher=ExpectationEventDispatcher(
                self.repository,
                receivers=(),
                max_attempts=3,
                trace_recorder_provider=lambda: self.recorder,
            ),
            max_open=8,
            timeline_turns=3,
            grounds_reader=_NoTexts(),
            max_grounds_questions=4,
            grounds_min_probability=0.5,
            trace_recorder_provider=lambda: self.recorder,
            field_selections=self.selections,
        )

    def form(self, expectation_id: str, content: str) -> None:
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
            ),
            [],
        )

    def turn(self) -> Any:
        self.repository.advance_turn(RIO)
        return self.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

    def selection(self) -> Any:
        assert self.selections is not None
        return self.selections.for_prompt(RIO, current_turn=self.repository.current_turn(RIO))

    def settlement(self) -> dict[str, Any]:
        return self.recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)[-1]


class TestFieldsAreAskedEveryTurn:
    """欄の問いが、予期の有無にかかわらず毎ターン 1 回の呼び出しに載ることを保証する。"""

    def test_turn_without_expectations_asks_only_the_field_questions(self) -> None:
        """予期が 1 件も無いターンにも Jev を 1 回呼び、欄の問いだけを並べて、選択を次のプロンプトへ渡す。"""
        port = ScriptedJudgmentPort(_fields({SituationField.HAPPENING}))
        harness = _Harness(port)

        report = harness.turn()

        assert len(port.calls) == 1
        assert set(port.calls[0][1]) == FIELD_NAMES
        assert report.skipped_reason == SKIPPED_NOTHING_TO_JUDGE
        assert harness.selection().kept == frozenset({SituationField.HAPPENING})
        assert harness.settlement()["field_selection"]["kept_fields"] == ["いま起きたこと"]

    def test_field_questions_ride_on_the_settlement_call(self) -> None:
        """予期があるターンは、形と当否の問いと同じ 1 回の呼び出しに欄の問いを足す。"""
        port = ScriptedJudgmentPort({"shape_0": "settleable", **_fields({SituationField.INTENT})})
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert len(port.calls) == 1
        assert FIELD_NAMES <= set(port.calls[0][1])
        assert "shape_0" in port.calls[0][1]
        assert harness.selection().kept == frozenset({SituationField.INTENT})

    def test_without_selection_store_expectation_turns_ask_no_field_questions(self) -> None:
        """選択の保存先を渡さなければ、予期があるターンの問いにも欄の問いは混ざらない。"""
        port = ScriptedJudgmentPort({"shape_0": "settleable"})
        harness = _Harness(port, with_fields=False)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert FIELD_NAMES.isdisjoint(port.calls[0][1])

    def test_without_selection_store_nothing_extra_is_asked(self) -> None:
        """選択の保存先を渡さなければ、予期の無いターンには Jev を呼ばず、欄の問いも出さない。"""
        port = ScriptedJudgmentPort()
        harness = _Harness(port, with_fields=False)

        harness.turn()

        assert port.calls == []
        assert harness.settlement()["field_selection"] is None


class TestFieldAnswersAreReadApartFromExpectations:
    """欄の答えと予期の判定が、片方の崩れでもう片方を巻き込まないことを保証する。"""

    def test_missing_expectation_answer_keeps_the_field_selection(self) -> None:
        """予期の答えが欠けても、欄の選択は採り、予期の判定だけを縮退させる。"""
        port = _DroppingPort(
            {"shape_0": "settleable", **_fields({SituationField.COUNTERPART})}, drop="shape_0"
        )
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        report = harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert report.skipped_reason == SKIPPED_JUDGMENT_UNAVAILABLE
        assert harness.selection().kept == frozenset({SituationField.COUNTERPART})
        assert harness.selection().degraded_reason is None

    def test_missing_field_answer_keeps_the_expectation_verdict(self) -> None:
        """欄の答えが欠けても、予期の形は判定し、欄の選択だけを全部の欄に縮退させる。"""
        port = _DroppingPort(
            {"shape_0": "true_either_way", **_fields(set())},
            drop=field_question_name(SituationField.INTENT),
        )
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "雨が降るか降らないか")

        report = harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert report.judged is True
        assert [(t["step"], t["verdict"]) for t in report.transitions] == [
            ("shape", "true_either_way")
        ]
        assert harness.selection().degraded_reason == DEGRADED_ANSWER_MISSING

    def test_unavailable_judgment_degrades_the_field_selection(self) -> None:
        """Jev が答えなければ、欄の選択は全部の欄に縮退し、理由を持って次のプロンプトへ渡る。"""
        port = ScriptedJudgmentPort(
            TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT")
        )
        harness = _Harness(port)

        harness.turn()

        selection = harness.selection()
        assert selection.degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE
        assert "TYPED_JUDGMENT_TIMEOUT" in selection.degraded_detail
        assert harness.settlement()["field_selection"]["degraded_reason"] == (
            DEGRADED_JUDGMENT_UNAVAILABLE
        )

    def test_fields_only_turn_records_why_the_judgment_was_unavailable(self) -> None:
        """予期の無いターンに欄だけを問って Jev が答えなければ、清算の trace にも答えが得られなかった理由を残す。"""
        port = ScriptedJudgmentPort(
            TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT")
        )
        harness = _Harness(port)

        harness.turn()

        payload = harness.settlement()
        assert payload["skipped_reason"] == SKIPPED_NOTHING_TO_JUDGE
        assert "TYPED_JUDGMENT_TIMEOUT" in payload["unavailable_reason"]

    def test_fields_only_turn_records_the_raw_answers(self) -> None:
        """予期の無いターンに欄だけを問えば、清算の trace に欄の問いの生の答えも残す。"""
        harness = _Harness(ScriptedJudgmentPort(_fields({SituationField.INTENT})))

        harness.turn()

        answers = harness.settlement()["answers"]
        assert set(answers) == FIELD_NAMES
        assert answers[field_question_name(SituationField.INTENT)]["value"] == KEEP

    def test_unavailable_judgment_with_expectations_degrades_both(self) -> None:
        """予期があるターンに Jev が答えなければ、予期の判定と欄の選択の両方が縮退し、前のターンの選択を残さない。"""
        port = ScriptedJudgmentPort(
            _fields({SituationField.INTENT}),
            TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT"),
        )
        harness = _Harness(port)
        harness.turn()
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        report = harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert report.skipped_reason == SKIPPED_JUDGMENT_UNAVAILABLE
        assert harness.selection().degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE

    def test_second_settlement_of_the_same_turn_keeps_the_first_selection(self) -> None:
        """同じターンを 2 回清算しようとすると例外になるが、1 回目に選んだ欄は上書きせずに残す。"""
        harness = _Harness(ScriptedJudgmentPort(_fields({SituationField.INTENT})))
        harness.turn()

        with pytest.raises(ValueError, match="already been settled"):
            harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert harness.selection().kept == frozenset({SituationField.INTENT})

    def test_failure_after_fields_were_chosen_overwrites_them_and_reraises(self) -> None:
        """欄を採ったあとで清算が想定外の例外で落ちたら、採った欄を縮退で上書きしてから投げ直し、trace にも縮退を残す。"""
        port = ScriptedJudgmentPort({"shape_0": "settleable", **_fields({SituationField.INTENT})})
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        def _broken_save(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("disk full")

        harness.repository.save = _broken_save  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert harness.selection().degraded_reason == SKIPPED_SETTLEMENT_FAILED
        assert harness.settlement()["field_selection"]["degraded_reason"] == (
            SKIPPED_SETTLEMENT_FAILED
        )
