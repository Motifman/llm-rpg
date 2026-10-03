"""信念を作る直前に、形と同じ意味の既存の信念を Jev に 1 回で問う仕様 (#1453)。

- 形が「いまの状況」なら作らない
- 同じ意味の既存の信念が選ばれたら、作る代わりにその信念を強める
- 判断が得られないときは作るを通し、縮退の理由を残す
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.belief_create_gate import (
    NO_SAME_MEANING,
    OUTCOME_CREATE,
    OUTCOME_SKIP_CURRENT_SITUATION,
    OUTCOME_STRENGTHEN,
    SAME_MEANING_QUESTION,
    SHAPE_CURRENT_SITUATION,
    SHAPE_QUESTION,
    BeliefCreateGate,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CharBigramBm25Narrower,
    TextCandidate,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)


class _ScriptedPort(ITypedJudgmentPort):
    """問いを記録し、決めた答えを決めた確信度で返す。"""

    def __init__(
        self,
        answers: Mapping[str, tuple[str, float | None]] | None = None,
        *,
        raises: BaseException | None = None,
        drop: str | None = None,
    ) -> None:
        self.answers = dict(answers or {})
        self.raises = raises
        self.drop = drop
        self.calls: list[tuple[Any, Mapping[str, Question]]] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append((state, questions))
        if self.raises is not None:
            raise self.raises
        out: dict[str, JudgmentResult] = {}
        for name, question in questions.items():
            assert isinstance(question, ChoiceQuestion)
            if name == self.drop:
                continue
            value, confidence = self.answers.get(
                name, (next(iter(question.options)), 0.99)
            )
            out[name] = JudgmentResult(
                value=value,
                probabilities={value: confidence or 0.0},
                confidence=confidence,
                source=JudgmentSource.JEV,
                latency_ms=12.0,
            )
        return out


_EXISTING = [
    TextCandidate("sem-shell", "腐った貝は食べると毒になる"),
    TextCandidate("sem-cave", "北の洞窟は危険だ"),
    TextCandidate("sem-ada", "エイダは枯れ葉の入手に協力的だ"),
]
_NEW_TEXT = "腐った貝を食べると毒に当たる"


def _gate(port: ITypedJudgmentPort, *, top_k: int = 2, min_confidence: float = 0.6):
    return BeliefCreateGate(
        judgment_port=port,
        narrower=CharBigramBm25Narrower(),
        top_k=top_k,
        min_confidence=min_confidence,
    )


class TestTheShapeQuestion:
    """形が「いまの状況」の文を信念にしないことを保証する。"""

    def test_a_current_situation_is_not_created(self) -> None:
        """形の答えが「いまの状況」で確信度が閾値以上なら、作らないと決める。"""
        port = _ScriptedPort({SHAPE_QUESTION: (SHAPE_CURRENT_SITUATION, 0.9)})

        review = _gate(port).review("ノアとリオは干潟に向かっている", _EXISTING)

        assert review.outcome == OUTCOME_SKIP_CURRENT_SITUATION

    def test_a_current_situation_wins_over_a_same_meaning_answer(self) -> None:
        """同じ意味の信念が選ばれても、形がいまの状況なら強めもしない。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: (SHAPE_CURRENT_SITUATION, 0.9),
                SAME_MEANING_QUESTION: ("腐った貝は食べると毒になる", 0.9),
            }
        )

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_SKIP_CURRENT_SITUATION
        assert review.target_key is None


class TestTheSameMeaningQuestion:
    """同じ意味の既存の信念があれば作る代わりに強めることを保証する。"""

    def test_a_same_meaning_belief_turns_create_into_strengthen(self) -> None:
        """同じ意味の答えが既存の信念の文なら、その信念の key を強める先にする。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: ("腐った貝は食べると毒になる", 0.8),
            }
        )

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_STRENGTHEN
        assert review.target_key == "sem-shell"

    def test_no_same_meaning_creates(self) -> None:
        """同じ意味の答えが「該当なし」なら、作る。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: (NO_SAME_MEANING, 0.9),
            }
        )

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.target_key is None

    def test_options_are_the_top_k_candidates_and_none(self) -> None:
        """選択肢は BM25 の上位 K 件の文と「該当なし」だけで、K を超えて並べない。"""
        port = _ScriptedPort()

        _gate(port, top_k=1).review(_NEW_TEXT, _EXISTING)

        _, questions = port.calls[0]
        options = questions[SAME_MEANING_QUESTION].options
        assert list(options) == [NO_SAME_MEANING, "腐った貝は食べると毒になる"]

    def test_identical_candidate_texts_become_one_option(self) -> None:
        """同じ文の既存の信念が 2 件あっても選択肢は 1 つで、上位の key を強める。"""
        existing = [
            TextCandidate("sem-first", "腐った貝は食べると毒になる"),
            TextCandidate("sem-second", "腐った貝は食べると毒になる"),
        ]
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: ("腐った貝は食べると毒になる", 0.9),
            }
        )

        review = _gate(port, top_k=5).review(_NEW_TEXT, existing)

        _, questions = port.calls[0]
        assert list(questions[SAME_MEANING_QUESTION].options) == [
            NO_SAME_MEANING,
            "腐った貝は食べると毒になる",
        ]
        assert review.target_key == "sem-first"

    def test_without_candidates_only_the_shape_is_asked(self) -> None:
        """近い既存の信念が無ければ、同じ意味は問わず形だけを問う。"""
        port = _ScriptedPort()

        review = _gate(port).review(_NEW_TEXT, [TextCandidate("x", "ノアは嘘をつかない")])

        _, questions = port.calls[0]
        assert list(questions) == [SHAPE_QUESTION]
        assert review.outcome == OUTCOME_CREATE

    def test_shape_and_same_meaning_are_asked_in_one_call(self) -> None:
        """形と同じ意味は同じ state で 1 回の呼び出しにまとめる。"""
        port = _ScriptedPort()

        _gate(port).review(_NEW_TEXT, _EXISTING)

        assert len(port.calls) == 1
        state, questions = port.calls[0]
        assert set(questions) == {SHAPE_QUESTION, SAME_MEANING_QUESTION}
        assert _NEW_TEXT in str(state)


class TestLowConfidenceAnswersAreNotUsed:
    """確信度が閾値に届かない答えでは振る舞いを変えないことを保証する。"""

    def test_a_low_confidence_situation_still_creates(self) -> None:
        """「いまの状況」でも確信度が閾値未満なら、作る。"""
        port = _ScriptedPort({SHAPE_QUESTION: (SHAPE_CURRENT_SITUATION, 0.4)})

        review = _gate(port, min_confidence=0.6).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE

    def test_a_low_confidence_same_meaning_still_creates(self) -> None:
        """同じ意味の信念が選ばれても確信度が閾値未満なら、作る。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: ("腐った貝は食べると毒になる", 0.4),
            }
        )

        review = _gate(port, min_confidence=0.6).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE

    def test_a_situation_exactly_at_the_threshold_is_used(self) -> None:
        """「いまの状況」の確信度が閾値ちょうどなら、その答えを採って作らない。"""
        port = _ScriptedPort({SHAPE_QUESTION: (SHAPE_CURRENT_SITUATION, 0.6)})

        review = _gate(port, min_confidence=0.6).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_SKIP_CURRENT_SITUATION

    def test_a_same_meaning_exactly_at_the_threshold_is_used(self) -> None:
        """同じ意味の答えの確信度が閾値ちょうどなら、その答えを採って強める。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: ("腐った貝は食べると毒になる", 0.6),
            }
        )

        review = _gate(port, min_confidence=0.6).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_STRENGTHEN

    def test_the_stub_port_lets_create_through(self) -> None:
        """決定論 stub は各問いの先頭 (「世界の決まり」と「該当なし」) を選ぶので、
        作るを通す。"""
        review = _gate(DeterministicTypedJudgmentPort(), top_k=1).review(
            _NEW_TEXT, _EXISTING
        )

        assert review.outcome == OUTCOME_CREATE


class TestWithoutAJudgmentCreateIsKept:
    """判断が得られないとき作るを通し、縮退の理由を残すことを保証する。"""

    def test_an_unavailable_judgment_creates_and_keeps_the_reason(self) -> None:
        """Jev が TypedJudgmentUnavailableException を投げたら、作るを通し error_code を残す。"""
        port = _ScriptedPort(
            raises=TypedJudgmentUnavailableException(
                "timeout", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED"
            )
        )

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "TYPED_JUDGMENT_TRANSPORT_FAILED"

    def test_an_unexpected_error_creates_and_keeps_the_reason(self) -> None:
        """想定外の例外でも作るを通し、理由を UNEXPECTED_ERROR として残す。"""
        port = _ScriptedPort(raises=RuntimeError("boom"))

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "UNEXPECTED_ERROR"

    def test_an_answer_outside_the_options_creates(self) -> None:
        """答えが選択肢に無い名前なら、判断が無かったとみなし作るを通す。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: ("存在しない信念", 0.9),
            }
        )

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "TYPED_JUDGMENT_ANSWER_INVALID"

    def test_a_shape_answer_outside_the_options_creates(self) -> None:
        """形の答えが選択肢に無い名前なら、作るを通し ANSWER_INVALID を残す。"""
        port = _ScriptedPort({SHAPE_QUESTION: ("天気", 0.9)})

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "TYPED_JUDGMENT_ANSWER_INVALID"

    def test_an_answer_without_confidence_creates(self) -> None:
        """確信度の無い Choice の答えは閾値と比べられないので、作るを通す。"""
        port = _ScriptedPort({SHAPE_QUESTION: (SHAPE_CURRENT_SITUATION, None)})

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "TYPED_JUDGMENT_ANSWER_INVALID"

    def test_a_missing_answer_creates(self) -> None:
        """問うた同じ意味の答えが返らなければ、作るを通し ANSWER_MISSING を残す。"""
        port = _ScriptedPort(drop=SAME_MEANING_QUESTION)

        review = _gate(port).review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "TYPED_JUDGMENT_ANSWER_MISSING"

    def test_a_candidate_reading_like_none_is_not_an_option(self) -> None:
        """「該当なし」と同じ文の既存の信念は、選択肢の「該当なし」と区別できないので並べない。"""
        port = _ScriptedPort()

        _gate(port).review("該当なし", [TextCandidate("odd", "該当なし")])

        _, questions = port.calls[0]
        assert list(questions) == [SHAPE_QUESTION]

    def test_a_failing_narrower_creates(self) -> None:
        """候補の絞り込みが例外を投げても、作るを通し UNEXPECTED_ERROR を残す。"""

        class _Broken(CharBigramBm25Narrower):
            def narrow(self, query, candidates, *, top_k):
                raise RuntimeError("embedding api down")

        gate = BeliefCreateGate(
            judgment_port=_ScriptedPort(),
            narrower=_Broken(),
            top_k=3,
            min_confidence=0.6,
        )

        review = gate.review(_NEW_TEXT, _EXISTING)

        assert review.outcome == OUTCOME_CREATE
        assert review.unavailable_reason == "UNEXPECTED_ERROR"

    def test_a_judged_review_has_no_unavailable_reason(self) -> None:
        """判断が得られた review の縮退理由は None で、縮退と区別できる。"""
        review = _gate(_ScriptedPort()).review(_NEW_TEXT, _EXISTING)

        assert review.unavailable_reason is None


class TestTheReviewIsReadableInTheTrace:
    """trace に、候補・答え・置き換えたかが残ることを保証する。"""

    def test_the_trace_payload_carries_candidates_answers_and_outcome(self) -> None:
        """payload に候補の key と文と score、形と同じ意味の答えと確信度、結果が載る。"""
        port = _ScriptedPort(
            {
                SHAPE_QUESTION: ("世界の決まり", 0.9),
                SAME_MEANING_QUESTION: ("腐った貝は食べると毒になる", 0.8),
            }
        )

        payload = _gate(port, top_k=1).review(_NEW_TEXT, _EXISTING).as_trace_payload()

        assert payload["text"] == _NEW_TEXT
        assert [c["key"] for c in payload["candidates"]] == ["sem-shell"]
        assert payload["candidates"][0]["score"] > 0
        assert payload["shape"] == "世界の決まり"
        assert payload["shape_confidence"] == pytest.approx(0.9)
        assert payload["same_meaning"] == "腐った貝は食べると毒になる"
        assert payload["same_meaning_confidence"] == pytest.approx(0.8)
        assert payload["outcome"] == OUTCOME_STRENGTHEN
        assert payload["target_key"] == "sem-shell"
        assert payload["narrower"] == "char_bigram_bm25"
        assert payload["top_k"] == 1
        assert payload["min_confidence"] == pytest.approx(0.6)
        assert payload["unavailable_reason"] is None


class TestConstruction:
    """不正な設定を構築時に弾くことを保証する。"""

    def test_top_k_below_one_is_rejected(self) -> None:
        """K が 1 未満なら ValueError。"""
        with pytest.raises(ValueError):
            _gate(_ScriptedPort(), top_k=0)

    @pytest.mark.parametrize("value", [0.0, 1.5])
    def test_min_confidence_outside_zero_one_is_rejected(self, value: float) -> None:
        """確信度の閾値が (0, 1] に無ければ ValueError。"""
        with pytest.raises(ValueError):
            _gate(_ScriptedPort(), min_confidence=value)
