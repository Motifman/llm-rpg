"""Jev を呼ばず、決めておいた答えを順に返す。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_rpg_world.being.application.rechoose_name import (
    NameChoiceAnswer,
    NameChoiceJudging,
    NameChoiceQuestion,
    NameChoiceUnavailable,
)


class ScriptedNameChoosing(NameChoiceJudging):
    """答えを使い切ったあとに呼ばれたら ``LookupError`` を投げる。"""

    def __init__(self, answers: Sequence[NameChoiceAnswer | NameChoiceUnavailable]) -> None:
        self._answers = list(answers)
        self.questions: list[tuple[Mapping[str, Any], NameChoiceQuestion]] = []

    def choose(self, state: Mapping[str, Any], question: NameChoiceQuestion) -> NameChoiceAnswer:
        self.questions.append((dict(state), question))
        if not self._answers:
            raise LookupError("no scripted answer is left")
        answer = self._answers.pop(0)
        if isinstance(answer, NameChoiceUnavailable):
            raise answer
        return answer


__all__ = ["ScriptedNameChoosing"]
