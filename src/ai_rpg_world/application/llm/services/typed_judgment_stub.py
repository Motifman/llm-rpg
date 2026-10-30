"""実 API を呼ばずに型付き判断の配線を確かめる決定論 stub (#1319)。

``smoke_stub`` profile で 3 用途の配線を通すために使う。

## 迷っている答えを返す

既定の答えは「どちらでもない」に寄せる。Noul は 0.5、Choice は一様分布で
confidence は ``1 / 選択肢数``、Score は中央の段階。

呼び出し側の閾値は「確信があるときだけ採る」ために置くので、この答えでは
**どの用途も閾値を超えず、現行の振る舞いのまま通る**。stub を挟んだ run が
現行と同じ結果になることを、値の側から保証する。

適当な値を返す stub にすると、smoke run の結果が説明できなくなる。乱数や
ハッシュ由来の値は使わない。

## 答えを固定したいとき

テストは ``answers`` に名前 → 値を渡して固定する。Noul は float、Choice は
選択肢名、Score は段階の番号か名前。
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any, Union

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    Question,
    ScoreQuestion,
)

#: 既定の Noul。真偽どちらにも寄らない。
_UNDECIDED_NOUL = 0.5


class DeterministicTypedJudgmentPort(ITypedJudgmentPort):
    """常に同じ答えを返す stub。実 API を呼ばない。"""

    def __init__(self, answers: Mapping[str, Any] | None = None) -> None:
        if answers is not None and not isinstance(answers, Mapping):
            raise TypeError("answers must be a mapping or None")
        self._answers: Mapping[str, Any] = dict(answers or {})

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        started = time.perf_counter()
        decided = {name: self._answer(name, question) for name, question in questions.items()}
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            name: JudgmentResult(
                value=value,
                probabilities=probabilities,
                confidence=confidence,
                source=JudgmentSource.STUB,
                latency_ms=elapsed_ms,
            )
            for name, (value, probabilities, confidence) in decided.items()
        }

    def _answer(self, name: str, question: Question) -> tuple[Any, Mapping[str, float], float | None]:
        if isinstance(question, NoulQuestion):
            return float(self._answers.get(name, _UNDECIDED_NOUL)), {}, None
        if isinstance(question, ChoiceQuestion):
            options = list(question.options.keys())
            if not options:
                raise ValueError(f"ChoiceQuestion {name!r} has no options")
            share = 1.0 / len(options)
            chosen = self._answers.get(name, options[0])
            if chosen not in question.options:
                raise ValueError(f"answers[{name!r}]={chosen!r} is not one of the offered options")
            return chosen, {option: share for option in options}, share
        if isinstance(question, ScoreQuestion):
            levels = list(question.levels)
            if not levels:
                raise ValueError(f"ScoreQuestion {name!r} has no levels")
            share = 1.0 / len(levels)
            requested = self._answers.get(name)
            index = self._level_index(name, levels, requested)
            return (
                float(index),
                {str(i): share for i in range(len(levels))},
                share,
            )
        raise TypeError(f"unsupported question type for {name!r}: {type(question)!r}")

    @staticmethod
    def _level_index(name: str, levels: Sequence[str], requested: Any | None) -> int:
        if requested is None:
            return (len(levels) - 1) // 2
        if isinstance(requested, int) and 0 <= requested < len(levels):
            return requested
        if isinstance(requested, str) and requested in levels:
            return list(levels).index(requested)
        raise ValueError(f"answers[{name!r}]={requested!r} is not one of the levels")


__all__ = ["DeterministicTypedJudgmentPort"]
