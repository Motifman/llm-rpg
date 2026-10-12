"""答えを台本で返す判断ポート。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    Question,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)


class ScriptedJudgmentPort(ITypedJudgmentPort):
    """呼ばれるたびに、渡された答えの並びを 1 つずつ返す判断ポート。受け取った state と質問を残す。

    答えに例外を置くと、その回はそれを投げる。並びに無い質問は stub と同じ迷った答えになる。
    """

    def __init__(self, *scripts: Mapping[str, Any] | Exception) -> None:
        self._scripts = list(scripts)
        self.calls: list[tuple[Any, Mapping[str, Question]]] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append((state, dict(questions)))
        script = self._scripts.pop(0) if self._scripts else {}
        if isinstance(script, Exception):
            raise script
        return DeterministicTypedJudgmentPort(script).judge(state, questions)


__all__ = ["ScriptedJudgmentPort"]
