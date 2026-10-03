"""自分の体の状態を「平常 / 注意 / 危機」の帯に丸める問いと、答えの読み方を保証する。"""

from __future__ import annotations

from ai_rpg_world.application.being.recall.body_band import (
    BODY_BAND_QUESTION,
    BODY_NOT_MENTIONED,
    BodyBand,
    BodyBandReading,
    body_band_from_answers,
    body_band_question,
)
from ai_rpg_world.application.being.recall.situation import (
    DEGRADED_ANSWER_MISSING,
    DEGRADED_JUDGMENT_UNAVAILABLE,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)


def _answers(value: str | None) -> dict:
    questions = {BODY_BAND_QUESTION: body_band_question("アリス")}
    script = {} if value is None else {BODY_BAND_QUESTION: value}
    return dict(DeterministicTypedJudgmentPort(script).judge({}, questions))


class TestQuestion:
    """帯の問いの形を保証する。"""

    def test_asks_one_of_the_three_bands_or_unknown_about_the_agent(self) -> None:
        """本人の体の状態を、平常・注意・危機か、体のことが書かれていないときの「分からない」から 1 つ選ばせる。"""
        question = body_band_question("アリス")

        assert isinstance(question, ChoiceQuestion)
        assert set(question.options) == {"平常", "注意", "危機", "分からない"}
        assert "アリス" in question.instructions


class TestReading:
    """答えから帯を読み、判断が得られないときは帯を付けない挙動を保証する。"""

    def test_reads_the_chosen_band_with_its_probabilities(self) -> None:
        """答えがあれば選ばれた帯を読み、確率と出所も trace に載せる。"""
        reading = body_band_from_answers(_answers("危機"))

        assert reading.band is BodyBand.CRISIS
        payload = reading.to_trace_payload()
        assert payload["band"] == "危機"
        assert payload["degraded_reason"] is None
        assert payload["source"] == "stub"
        assert set(payload["probabilities"]) == {"平常", "注意", "危機", "分からない"}

    def test_unknown_gives_no_band_and_says_the_body_was_not_mentioned(self) -> None:
        """「分からない」なら帯を付けず、体のことが書かれていなかったことを理由に持つ。平常には丸めない。"""
        reading = body_band_from_answers(_answers("分からない"))

        assert reading.band is None
        assert reading.degraded_reason == BODY_NOT_MENTIONED
        assert reading.source == "stub"

    def test_missing_answer_gives_no_band_with_a_reason(self) -> None:
        """答えが欠けていれば帯を付けず、欠けたことを理由に持つ。"""
        answers = _answers("注意")
        del answers[BODY_BAND_QUESTION]

        reading = body_band_from_answers(answers)

        assert reading.band is None
        assert reading.degraded_reason == DEGRADED_ANSWER_MISSING

    def test_unavailable_judgment_gives_no_band_with_the_error_code(self) -> None:
        """Jev が答えなければ帯を付けず、エラーコードを詳しい理由に持つ。"""
        exc = TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT")

        reading = BodyBandReading.unavailable(exc)

        assert reading.band is None
        assert reading.degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE
        assert "TYPED_JUDGMENT_TIMEOUT" in reading.degraded_detail


class TestSentence:
    """帯を状況の欄に入れるときの文を保証する。"""

    def test_sentence_carries_the_band_word(self) -> None:
        """帯の文には帯の語そのものが入る。書き込み時のキー (#1454) と語を揃えるため。"""
        for band in BodyBand:
            assert band.value in band.sentence()
