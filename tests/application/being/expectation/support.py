"""予期の清算と配信の試験で使う、trace を記録して読み返す口と、答えを台本で返す判断ポート。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from ai_rpg_world.application.being.recall.situation import (
    RECALL_FIELDS_QUESTION,
    SELECTABLE_FIELDS,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    Question,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEvent


class RecordingTraceRecorder(ITraceRecorder):
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(
        self,
        kind: str,
        *,
        tick: int | None = None,
        player_id: int | None = None,
        **payload: Any,
    ) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events) + 1,
            timestamp="2026-10-03T00:00:00Z",
            kind=kind,
            tick=tick,
            player_id=player_id,
            payload=dict(payload),
        )
        self.events.append(event)
        return event

    def close(self) -> None:
        return None

    def payloads(self, kind: str) -> list[dict[str, Any]]:
        return [event.payload for event in self.events if event.kind == kind]


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


def ranked_probabilities(*fields: Any) -> dict[str, float]:
    """欄を並べた順に確率が高くなるよう、選択肢ごとの確率を作る。並べなかった欄は低く同じ値にする。"""
    probabilities = {f.value: 0.02 for f in SELECTABLE_FIELDS}
    for rank, field in enumerate(fields):
        probabilities[field.value] = 0.5 - 0.1 * rank
    return probabilities


class FieldRankingPort(ScriptedJudgmentPort):
    """台本どおりに答えたうえで、欄を選ぶ問いの確率を呼ぶたびに ``rankings`` の順で差し替える。

    ``rankings`` を使い切ったあとは差し替えず、stub の一様な確率のまま答える。
    """

    def __init__(self, *scripts: Mapping[str, Any] | Exception, rankings: Sequence[Sequence[Any]]) -> None:
        super().__init__(*scripts)
        self._rankings = [tuple(r) for r in rankings]

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        answers = dict(super().judge(state, questions))
        if RECALL_FIELDS_QUESTION in answers and self._rankings:
            ranking = self._rankings.pop(0)
            answers[RECALL_FIELDS_QUESTION] = replace(
                answers[RECALL_FIELDS_QUESTION],
                value=ranking[0].value,
                probabilities=ranked_probabilities(*ranking),
            )
        return answers
