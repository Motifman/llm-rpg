from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import (
    NONE_APPLICABLE_OPTION,
    QUESTION_NAME,
    DiagnosisFallback,
    LoopDiagnosis,
    RepeatReason,
)


class _FixedPort(ITypedJudgmentPort):
    def __init__(
        self,
        *,
        value: str,
        probability: float,
        confidence: float | None,
    ) -> None:
        self.value = value
        self.probability = probability
        self.confidence = confidence
        self.calls: list[tuple[Any, Mapping[str, Question]]] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append((state, questions))
        return {
            QUESTION_NAME: JudgmentResult(
                value=self.value,
                probabilities={self.value: self.probability},
                confidence=self.confidence,
                source=JudgmentSource.STUB,
                latency_ms=3.0,
            )
        }


class _RaisingPort(ITypedJudgmentPort):
    def judge(self, state, questions):  # type: ignore[no-untyped-def]
        raise TypedJudgmentUnavailableException("timeout", error_code="TYPED_JUDGMENT_TIMEOUT")


class _EmptyPort(ITypedJudgmentPort):
    def judge(self, state, questions):  # type: ignore[no-untyped-def]
        return {}


_STATE = {"repeated_action": "`wait`"}


class TestTheQuestionOffersEveryReasonWithItsMeaning:
    """LoopDiagnosis が Jev に渡す選択肢が、理由の名前と意味の対であることを保証する。"""

    def test_options_are_every_reason_plus_none_applicable_each_with_a_meaning(self) -> None:
        """選択肢は RepeatReason の全件と「該当なし」で、どれも空でない意味の文を持つ。"""
        port = _FixedPort(value="waiting", probability=0.9, confidence=0.9)

        LoopDiagnosis(port=port).diagnose(_STATE)

        question = port.calls[0][1][QUESTION_NAME]
        assert isinstance(question, ChoiceQuestion)
        assert set(question.options) == {r.value for r in RepeatReason} | {
            NONE_APPLICABLE_OPTION
        }
        assert all(meaning for meaning in question.options.values())

    def test_the_state_is_passed_unchanged(self) -> None:
        """渡した state をそのまま判断ポートへ渡す。"""
        port = _FixedPort(value="waiting", probability=0.9, confidence=0.9)

        LoopDiagnosis(port=port).diagnose(_STATE)

        assert port.calls[0][0] == _STATE


class TestAdoptingOrFallingBack:
    """LoopDiagnosis が、該当なし以外の理由を選べば確率や確信によらず採ることを保証する。"""

    def test_adopts_the_chosen_reason_with_its_evidence(self) -> None:
        """確率 0.8・確信 0.7 で state_mistaken を選べば、その理由を採り縮退の理由は None。"""
        port = _FixedPort(value="state_mistaken", probability=0.8, confidence=0.7)

        judgment = LoopDiagnosis(port=port).diagnose(_STATE)

        assert judgment.reason is RepeatReason.STATE_MISTAKEN
        assert judgment.fallback is None
        assert judgment.chosen == "state_mistaken"
        assert judgment.probabilities == {"state_mistaken": 0.8}

    def test_adopts_the_reason_even_when_probability_and_confidence_are_low(self) -> None:
        """確率 0.53・確信 0.3 でも fixed_means を選べばその理由を採り、確率と確信は残す。"""
        port = _FixedPort(value="fixed_means", probability=0.53, confidence=0.3)

        judgment = LoopDiagnosis(port=port).diagnose(_STATE)

        assert judgment.reason is RepeatReason.FIXED_MEANS
        assert judgment.fallback is None
        assert judgment.probability == 0.53
        assert judgment.confidence == 0.3

    def test_none_applicable_falls_back_even_when_confident(self) -> None:
        """「該当なし」を確率 0.99 で選んでも理由は採らず、縮退の理由は NONE_APPLICABLE。"""
        port = _FixedPort(value=NONE_APPLICABLE_OPTION, probability=0.99, confidence=0.99)

        judgment = LoopDiagnosis(port=port).diagnose(_STATE)

        assert judgment.reason is None
        assert judgment.fallback is DiagnosisFallback.NONE_APPLICABLE

    def test_an_unknown_option_falls_back_as_unavailable(self) -> None:
        """選択肢に無い名前が返ったら理由は採らず、UNAVAILABLE と INVALID_RESPONSE を残す。"""
        port = _FixedPort(value="gather_more", probability=0.95, confidence=0.95)

        judgment = LoopDiagnosis(port=port).diagnose(_STATE)

        assert judgment.reason is None
        assert judgment.fallback is DiagnosisFallback.UNAVAILABLE
        assert judgment.unavailable_reason == "INVALID_RESPONSE"


class TestUnavailableJudgment:
    """判断が得られないとき、例外を外へ出さずに縮退の理由として返すことを保証する。"""

    def test_port_exception_becomes_unavailable_with_the_error_code(self) -> None:
        """判断ポートが TypedJudgmentUnavailableException を投げたら、UNAVAILABLE と error_code を返す。"""
        judgment = LoopDiagnosis(port=_RaisingPort()).diagnose(_STATE)

        assert judgment.reason is None
        assert judgment.fallback is DiagnosisFallback.UNAVAILABLE
        assert judgment.unavailable_reason == "TYPED_JUDGMENT_TIMEOUT"

    def test_missing_answer_becomes_unavailable(self) -> None:
        """答えの辞書に質問名が無ければ、UNAVAILABLE と ANSWER_MISSING を返す。"""
        judgment = LoopDiagnosis(port=_EmptyPort()).diagnose(_STATE)

        assert judgment.fallback is DiagnosisFallback.UNAVAILABLE
        assert judgment.unavailable_reason == "ANSWER_MISSING"

