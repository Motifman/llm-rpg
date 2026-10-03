"""ExpectationSettlementService が、次のターンの想起で残す欄を清算と同じ Jev の呼び出しで毎ターン問い、予期の判定とは分けて読む挙動を保証する (#1414)。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
    ranked_probabilities,
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
from ai_rpg_world.application.being.recall.body_band import BODY_BAND_QUESTION, BodyBand
from ai_rpg_world.application.being.recall.selection_store import NextTurnFieldSelections
from ai_rpg_world.application.being.recall.situation import (
    DEGRADED_ANSWER_MISSING,
    DEGRADED_JUDGMENT_UNAVAILABLE,
    RECALL_FIELDS_QUESTION,
    SELECTABLE_FIELDS,
    Situation,
    SituationField,
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
FIELD_NAMES = {RECALL_FIELDS_QUESTION}
RECALL_NAMES = FIELD_NAMES | {BODY_BAND_QUESTION}
_RANKING = "__ranking__"
INTENT_AND_HAPPENING = frozenset({SituationField.INTENT, SituationField.HAPPENING})


def _fields(*ranking: SituationField) -> dict[str, Any]:
    """台本に欄の順位を書く。欄を選ぶ問いの確率が、この順に高くなる。"""
    return {_RANKING: ranking}


class _Port(ScriptedJudgmentPort):
    """台本の ``_RANKING`` を、欄を選ぶ問いの確率に変えて答える。"""

    def judge(self, state: Any, questions: Any) -> Any:
        script = self._scripts[0] if self._scripts else {}
        ranking: tuple[SituationField, ...] = ()
        if isinstance(script, dict) and _RANKING in script:
            ranking = script[_RANKING]
            self._scripts[0] = {k: v for k, v in script.items() if k != _RANKING}
        answers = dict(super().judge(state, questions))
        if ranking and RECALL_FIELDS_QUESTION in answers:
            answers[RECALL_FIELDS_QUESTION] = replace(
                answers[RECALL_FIELDS_QUESTION],
                value=ranking[0].value,
                probabilities=ranked_probabilities(*ranking),
            )
        return answers


class _DroppingPort(_Port):
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
    def __init__(
        self, port: ScriptedJudgmentPort, *, with_fields: bool = True, keep: int = 2
    ) -> None:
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
            fields_to_keep=keep,
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

    def band(self) -> Any:
        assert self.selections is not None
        return self.selections.band_for_prompt(
            RIO, current_turn=self.repository.current_turn(RIO)
        )

    def selection(self) -> Any:
        assert self.selections is not None
        return self.selections.for_prompt(RIO, current_turn=self.repository.current_turn(RIO))

    def settlement(self) -> dict[str, Any]:
        return self.recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)[-1]


class TestFieldsAreAskedEveryTurn:
    """欄の問いが、予期の有無にかかわらず毎ターン 1 回の呼び出しに載ることを保証する。"""

    def test_turn_without_expectations_asks_only_the_field_questions(self) -> None:
        """予期が 1 件も無いターンにも Jev を 1 回呼び、欄を選ぶ問いと体の帯の問いだけを並べて、確率の上位 2 つの欄を次のプロンプトへ渡す。"""
        port = _Port(_fields(SituationField.HAPPENING, SituationField.INTENT))
        harness = _Harness(port)

        report = harness.turn()

        assert len(port.calls) == 1
        assert set(port.calls[0][1]) == RECALL_NAMES
        assert report.skipped_reason == SKIPPED_NOTHING_TO_JUDGE
        assert harness.selection().kept == INTENT_AND_HAPPENING
        assert harness.settlement()["field_selection"]["kept_fields"] == [
            "やろうとしていること",
            "いま起きたこと",
        ]

    def test_situation_values_are_shown_in_the_state(self) -> None:
        """欄を問うターンは、渡されたいまの状況の欄の値を state の「いまの状況」に載せる。値の無い欄は空で見せる。"""
        port = _Port()
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)

        harness.service.settle_turn(
            RIO,
            self_name="リオ",
            material=TurnMaterial(),
            situation=Situation(place=("干潟",), happening=("カニに挟まれた",)),
        )

        shown = port.calls[0][0]["いまの状況"]
        assert shown["いま起きたこと"] == ["カニに挟まれた"]
        assert shown["場所"] == ["干潟"]
        assert shown["未解決のこと"] == []

    def test_fields_to_keep_applies_on_turns_with_expectations(self) -> None:
        """予期があるターンにも、残す欄の数が効く。"""
        port = _Port({"shape_0": "settleable", **_fields(SituationField.INTENT, SituationField.HAPPENING)})
        harness = _Harness(port, keep=1)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert harness.selection().kept == frozenset({SituationField.INTENT})

    def test_situation_values_are_shown_on_turns_with_expectations(self) -> None:
        """予期があるターンも、形と当否の問いと同じ state にいまの状況の欄の値を載せる。"""
        port = _Port({"shape_0": "settleable"})
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(
            RIO,
            self_name="リオ",
            material=TurnMaterial(),
            situation=Situation(counterpart=("トム",)),
        )

        assert port.calls[0][0]["いまの状況"]["相手"] == ["トム"]

    def test_trace_says_whether_the_situation_was_shown_and_why_not(self) -> None:
        """清算の trace の欄の選択に、残す数、値を見せたか、呼び出し側が渡した事情を残す。"""
        harness = _Harness(_Port())
        harness.repository.advance_turn(RIO)

        harness.service.settle_turn(
            RIO,
            self_name="リオ",
            material=TurnMaterial(),
            situation_note={"unavailable": "RuntimeError: broken"},
        )

        chosen = harness.settlement()["field_selection"]
        assert chosen["keep"] == 2
        assert chosen["situation_shown"] is False
        assert chosen["situation_note"] == {"unavailable": "RuntimeError: broken"}
        assert "いまの状況" not in harness.settlement()["state"]

    @pytest.mark.parametrize("keep", [0, 6])
    def test_rejects_fields_to_keep_outside_one_to_five(self, keep: int) -> None:
        """残す欄の数が 1〜5 の外なら、作る時点で ValueError を投げる。毎ターンの清算で落ちないように。"""
        with pytest.raises(ValueError):
            _Harness(_Port(), keep=keep)

    def test_fields_to_keep_sets_how_many_fields_remain(self) -> None:
        """残す欄の数に 1 を渡すと、いちばん確率の高い欄だけを次のプロンプトへ渡す。"""
        harness = _Harness(_Port(_fields(SituationField.INTENT, SituationField.HAPPENING)), keep=1)

        harness.turn()

        assert harness.selection().kept == frozenset({SituationField.INTENT})

    def test_field_questions_ride_on_the_settlement_call(self) -> None:
        """予期があるターンは、形と当否の問いと同じ 1 回の呼び出しに欄の問いを足す。"""
        port = _Port({"shape_0": "settleable", **_fields(SituationField.INTENT, SituationField.HAPPENING)})
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert len(port.calls) == 1
        assert FIELD_NAMES <= set(port.calls[0][1])
        assert "shape_0" in port.calls[0][1]
        assert harness.selection().kept == INTENT_AND_HAPPENING

    def test_without_selection_store_the_situation_is_not_shown(self) -> None:
        """欄を問わない清算は、いまの状況を渡されても state に載せない。いままでの清算の state を変えない。"""
        port = _Port({"shape_0": "settleable"})
        harness = _Harness(port, with_fields=False)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(
            RIO, self_name="リオ", material=TurnMaterial(), situation=Situation(place=("干潟",))
        )

        assert "いまの状況" not in port.calls[0][0]
        assert harness.service.asks_fields is False

    def test_without_selection_store_expectation_turns_ask_no_field_questions(self) -> None:
        """選択の保存先を渡さなければ、予期があるターンの問いにも欄の問いは混ざらない。"""
        port = _Port({"shape_0": "settleable"})
        harness = _Harness(port, with_fields=False)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert FIELD_NAMES.isdisjoint(port.calls[0][1])

    def test_without_selection_store_nothing_extra_is_asked(self) -> None:
        """選択の保存先を渡さなければ、予期の無いターンには Jev を呼ばず、欄の問いも出さない。"""
        port = _Port()
        harness = _Harness(port, with_fields=False)

        harness.turn()

        assert port.calls == []
        assert harness.settlement()["field_selection"] is None


class TestFieldAnswersAreReadApartFromExpectations:
    """欄の答えと予期の判定が、片方の崩れでもう片方を巻き込まないことを保証する。"""

    def test_missing_expectation_answer_keeps_the_field_selection(self) -> None:
        """予期の答えが欠けても、欄の選択は採り、予期の判定だけを縮退させる。"""
        port = _DroppingPort(
            {"shape_0": "settleable", **_fields(SituationField.COUNTERPART, SituationField.UNRESOLVED)}, drop="shape_0"
        )
        harness = _Harness(port)
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        report = harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert report.skipped_reason == SKIPPED_JUDGMENT_UNAVAILABLE
        assert harness.selection().kept == frozenset(
            {SituationField.COUNTERPART, SituationField.UNRESOLVED}
        )
        assert harness.selection().degraded_reason is None

    def test_missing_field_answer_keeps_the_expectation_verdict(self) -> None:
        """欄の答えが欠けても、予期の形は判定し、欄の選択だけを全部の欄に縮退させる。"""
        port = _DroppingPort(
            {"shape_0": "true_either_way", **_fields()},
            drop=RECALL_FIELDS_QUESTION,
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
        port = _Port(
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
        port = _Port(
            TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT")
        )
        harness = _Harness(port)

        harness.turn()

        payload = harness.settlement()
        assert payload["skipped_reason"] == SKIPPED_NOTHING_TO_JUDGE
        assert "TYPED_JUDGMENT_TIMEOUT" in payload["unavailable_reason"]

    def test_fields_only_turn_records_the_raw_answers_with_probabilities(self) -> None:
        """予期の無いターンに欄だけを問えば、清算の trace に欄の問いの生の答えも残す。"""
        harness = _Harness(_Port(_fields(SituationField.INTENT, SituationField.HAPPENING)))

        harness.turn()

        answers = harness.settlement()["answers"]
        assert set(answers) == RECALL_NAMES
        assert answers[RECALL_FIELDS_QUESTION]["value"] == "やろうとしていること"
        probabilities = answers[RECALL_FIELDS_QUESTION]["probabilities"]
        assert probabilities["やろうとしていること"] > probabilities["相手"]

    def test_unavailable_judgment_with_expectations_degrades_both(self) -> None:
        """予期があるターンに Jev が答えなければ、予期の判定と欄の選択の両方が縮退し、前のターンの選択を残さない。"""
        port = _Port(
            _fields(SituationField.INTENT, SituationField.HAPPENING),
            TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT"),
        )
        harness = _Harness(port)
        harness.turn()
        harness.repository.advance_turn(RIO)
        harness.form("e1", "トムが麦束を焼いてくれる")

        report = harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert report.skipped_reason == SKIPPED_JUDGMENT_UNAVAILABLE
        assert harness.selection().degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE
        assert harness.band().band is None
        assert harness.band().degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE

    def test_second_settlement_of_the_same_turn_keeps_the_first_selection(self) -> None:
        """同じターンを 2 回清算しようとすると例外になるが、1 回目に選んだ欄は上書きせずに残す。"""
        harness = _Harness(_Port(_fields(SituationField.INTENT, SituationField.HAPPENING)))
        harness.turn()

        with pytest.raises(ValueError, match="already been settled"):
            harness.service.settle_turn(RIO, self_name="リオ", material=TurnMaterial())

        assert harness.selection().kept == INTENT_AND_HAPPENING

    def test_failure_after_fields_were_chosen_overwrites_them_and_reraises(self) -> None:
        """欄を採ったあとで清算が想定外の例外で落ちたら、採った欄を縮退で上書きしてから投げ直し、trace にも縮退を残す。"""
        port = _Port({"shape_0": "settleable", **_fields(SituationField.INTENT, SituationField.HAPPENING)})
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
        assert harness.band().degraded_reason == SKIPPED_SETTLEMENT_FAILED
        assert harness.settlement()["field_selection"]["body_band"]["band"] is None


class TestBodyBand:
    """自分の体の帯が、欄と同じ呼び出しで問われ、欄とは分けて読まれることを保証する。"""

    def test_band_is_read_and_handed_to_the_next_prompt(self) -> None:
        """帯の答えを読み、欄の選択と一緒に次のプロンプトへ渡し、清算の trace にも残す。"""
        harness = _Harness(_Port({BODY_BAND_QUESTION: "危機", **_fields()}))

        harness.turn()

        assert harness.band().band is BodyBand.CRISIS
        assert harness.settlement()["field_selection"]["body_band"]["band"] == "危機"

    def test_missing_band_answer_keeps_the_field_selection(self) -> None:
        """帯の答えが欠けても欄の選択は採り、帯だけを付けない。"""
        port = _DroppingPort(_fields(SituationField.INTENT, SituationField.HAPPENING), drop=BODY_BAND_QUESTION)
        harness = _Harness(port)

        harness.turn()

        assert harness.selection().kept == INTENT_AND_HAPPENING
        assert harness.band().band is None
        assert harness.band().degraded_reason == DEGRADED_ANSWER_MISSING

    def test_unavailable_judgment_leaves_no_band(self) -> None:
        """Jev が答えなければ帯も付けず、理由を持つ。"""
        port = _Port(
            TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT")
        )
        harness = _Harness(port)

        harness.turn()

        assert harness.band().band is None
        assert harness.band().degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE
