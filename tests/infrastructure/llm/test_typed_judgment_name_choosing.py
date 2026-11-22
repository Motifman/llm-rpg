from __future__ import annotations

import pytest
from tests.judgment_helpers import ScriptedJudgmentPort

from ai_rpg_world.application.llm.ports.typed_judgment_port import ChoiceQuestion, TypedJudgmentUnavailableException
from ai_rpg_world.being.application.rechoose_name import NameChoiceQuestion, NameChoiceUnavailable
from ai_rpg_world.infrastructure.llm.typed_judgment_name_choosing import QUESTION_NAME, TypedJudgmentNameChoosing

QUESTION = NameChoiceQuestion(
    instructions="書かれた名前 written_name は、相手としていま選べる候補のどれを指しているか。",
    options={"金庫": None, "__no_match__": "一覧のどれにも当たらない"},
)


class TestTypedJudgmentNameChoosing:
    """TypedJudgmentNameChoosing が、Being の名前の問いを型付きの判断の Choice に写し、答えを Being の形に戻すことを保証する。"""

    def test_question_goes_to_the_port_as_one_choice_with_the_same_state(self) -> None:
        """state はそのまま、問いは指示と選択肢を変えずに 1 件の ChoiceQuestion として判断に渡る。"""
        port = ScriptedJudgmentPort({QUESTION_NAME: "金庫"})

        TypedJudgmentNameChoosing(port).choose({"written_name": "safe"}, QUESTION)

        [(state, questions)] = port.calls
        assert state == {"written_name": "safe"}
        assert questions == {
            QUESTION_NAME: ChoiceQuestion(instructions=QUESTION.instructions, options=QUESTION.options)
        }

    def test_answer_keeps_the_choice_its_probabilities_and_where_it_came_from(self) -> None:
        """判断が「金庫」を選ぶと、選んだ名前・選択肢ごとの確率・確信・出どころ (stub) が答えに残る。"""
        port = ScriptedJudgmentPort({QUESTION_NAME: "金庫"})

        answer = TypedJudgmentNameChoosing(port).choose({}, QUESTION)

        assert answer.value == "金庫"
        assert answer.probabilities == {"金庫": 0.5, "__no_match__": 0.5}
        assert answer.confidence == 0.5
        assert answer.source == "stub"

    def test_unavailable_judgment_is_raised_with_its_error_code(self) -> None:
        """判断が TYPED_JUDGMENT_RATE_LIMITED で得られないと、同じ code を持つ NameChoiceUnavailable を投げる。"""
        port = ScriptedJudgmentPort(TypedJudgmentUnavailableException("429", error_code="TYPED_JUDGMENT_RATE_LIMITED"))

        with pytest.raises(NameChoiceUnavailable) as raised:
            TypedJudgmentNameChoosing(port).choose({}, QUESTION)

        assert raised.value.code == "TYPED_JUDGMENT_RATE_LIMITED"
