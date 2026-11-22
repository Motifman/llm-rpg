"""Being の名前の選び直しを、型付きの判断 (Jev) に問う。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.being.application.rechoose_name import (
    NameChoiceAnswer,
    NameChoiceJudging,
    NameChoiceQuestion,
    NameChoiceUnavailable,
)

QUESTION_NAME = "being_name_rechoice"


class TypedJudgmentNameChoosing(NameChoiceJudging):
    def __init__(self, port: ITypedJudgmentPort) -> None:
        self._port = port

    def choose(self, state: Mapping[str, Any], question: NameChoiceQuestion) -> NameChoiceAnswer:
        try:
            answers = self._port.judge(
                state, {QUESTION_NAME: ChoiceQuestion(instructions=question.instructions, options=question.options)}
            )
        except TypedJudgmentUnavailableException as exc:
            raise NameChoiceUnavailable(str(exc), code=exc.error_code) from exc
        answer = answers[QUESTION_NAME]
        return NameChoiceAnswer(
            value=str(answer.value),
            probabilities=dict(answer.probabilities),
            confidence=answer.confidence,
            source=answer.source.value,
            latency_ms=answer.latency_ms,
        )


__all__ = ["QUESTION_NAME", "TypedJudgmentNameChoosing"]
