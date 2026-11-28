"""候補に当たらなかった名前を、渡した候補から意味で選び直す。

「該当なし」を必ず選択肢に入れる。入れないと、どれにも当たらない名前でも一番近いものに寄る。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from semantic_resolver import (
    Assessment,
    BackendError,
    Candidate,
    Judgment,
    ResolutionRequest,
    Resolved,
    SemanticResolver,
)

from ai_rpg_world.being.application.action_tools import ActionTools

#: 候補の名前と重ならない形にする。``none`` のような名前だと、世界にそういう候補があるかのように読める。
NO_MATCH_OPTION = "__no_match__"


@dataclass(frozen=True)
class NameChoiceQuestion:
    """``options`` は選択肢の名前 → 意味。意味の無い選択肢は None。"""

    instructions: str
    options: Mapping[str, str | None]


@dataclass(frozen=True)
class NameChoiceAnswer:
    value: str
    probabilities: Mapping[str, float]
    confidence: float | None
    source: str
    latency_ms: float | None


class NameChoiceUnavailable(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class NameChoiceJudging(ABC):
    @abstractmethod
    def choose(self, state: Mapping[str, Any], question: NameChoiceQuestion) -> NameChoiceAnswer:
        """判断を得られなければ ``NameChoiceUnavailable`` を投げる。"""


@dataclass(frozen=True)
class NameRechoice:
    """選び直しを問うた結果。採らなかった判断も残す。残さないと、問わなかったのか問って採らなかったのかを
    記録から見分けられず、下限を動かす判断ができない。
    """

    tool: str
    argument: str
    original: str
    replaced_with: str | None
    chosen: str | None
    probability: float | None
    confidence: float | None
    min_confidence: float
    accepted: bool
    latency_ms: float | None = None
    source: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class NamesMatched:
    """``arguments`` は候補の名前に合わせた引数。``rechoices`` は選び直しを問うた順の結果。"""

    arguments: Mapping[str, object]
    rechoices: tuple[NameRechoice, ...]


class RechooseName:
    def __init__(self, judging: NameChoiceJudging, *, min_confidence: float) -> None:
        if not 0.0 < float(min_confidence) <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        self._min_confidence = float(min_confidence)
        self._resolver = SemanticResolver(backend=_Backend(judging), policy=_Policy(self._min_confidence))

    def match_names(
        self,
        tools: ActionTools,
        *,
        tool_name: str,
        arguments: Mapping[str, object],
        inner_thought: str | None,
    ) -> NamesMatched:
        """候補に当たらない名前だけを選び直す。"""
        rechoices: list[NameRechoice] = []

        def rechoose(written: str, label: str, candidates: Mapping[str, str | None], parent: str | None) -> str | None:
            rechoice = self.rechoose(
                written, label=label, candidates=candidates, parent=parent, tool=tool_name, inner_thought=inner_thought
            )
            rechoices.append(rechoice)
            return rechoice.replaced_with

        matched = tools.with_names_matched(tool_name, arguments, rechoose)
        return NamesMatched(arguments=matched, rechoices=tuple(rechoices))

    def rechoose(
        self,
        written: str,
        *,
        label: str,
        candidates: Mapping[str, str | None],
        parent: str | None,
        tool: str,
        inner_thought: str | None,
    ) -> NameRechoice:
        state: dict[str, Any] = {"written_name": written, "argument": label, "tool": tool}
        if parent is not None:
            state["under"] = parent
        state["candidates"] = dict(candidates)
        thought = (inner_thought or "").strip()
        if thought:
            state["inner_thought"] = thought
        try:
            result = self._resolver.resolve(
                value=written,
                candidates=[Candidate(name, description or name) for name, description in candidates.items()],
                context=state,
            )
        except BackendError as exc:
            return NameRechoice(
                tool=tool,
                argument=label,
                original=written,
                replaced_with=None,
                chosen=None,
                probability=None,
                confidence=None,
                min_confidence=self._min_confidence,
                accepted=False,
                unavailable_reason=exc.code,
            )
        assert result.judgment is not None
        answer: NameChoiceAnswer = result.judgment.evidence
        accepted = isinstance(result, Resolved)
        return NameRechoice(
            tool=tool,
            argument=label,
            original=written,
            replaced_with=str(result.value) if isinstance(result, Resolved) else None,
            chosen=result.judgment.value,
            probability=answer.probabilities.get(answer.value),
            confidence=answer.confidence,
            min_confidence=self._min_confidence,
            accepted=accepted,
            latency_ms=answer.latency_ms,
            source=answer.source,
        )


class _Backend:
    def __init__(self, judging: NameChoiceJudging) -> None:
        self._judging = judging

    def judge(self, request: ResolutionRequest) -> Judgment[NameChoiceAnswer]:
        options = {c.value: (None if c.description == c.value else c.description) for c in request.candidates}
        if NO_MATCH_OPTION in options:
            raise BackendError("a candidate collides with the no-match option")
        question = NameChoiceQuestion(
            instructions=(
                f"書かれた名前 written_name は、{request.context.get('argument', '')}としていま選べる候補のどれを"
                f"指しているか。どれでもなければ {NO_MATCH_OPTION} を選ぶ。"
            ),
            options={**options, NO_MATCH_OPTION: "一覧のどれにも当たらない"},
        )
        try:
            answer = self._judging.choose(request.context, question)
        except NameChoiceUnavailable as exc:
            raise BackendError(str(exc), code=exc.code) from exc
        return Judgment(
            value=None if answer.value == NO_MATCH_OPTION else answer.value,
            evidence=answer,
            backend=answer.source,
            model="",
            latency_ms=answer.latency_ms or 0.0,
        )


class _Policy:
    def __init__(self, minimum: float) -> None:
        self._minimum = minimum

    def assess(self, judgment: Judgment[NameChoiceAnswer]) -> Assessment:
        answer = judgment.evidence
        probability = answer.probabilities.get(answer.value)
        accepted = (
            probability is not None
            and probability >= self._minimum
            and (answer.confidence is None or answer.confidence >= self._minimum)
        )
        return Assessment(
            reason="accepted" if accepted else "below_threshold",
            thresholds={"min_probability": self._minimum, "min_confidence": self._minimum},
        )


__all__ = [
    "NO_MATCH_OPTION",
    "NameChoiceAnswer",
    "NameChoiceJudging",
    "NameChoiceQuestion",
    "NameChoiceUnavailable",
    "NameRechoice",
    "NamesMatched",
    "RechooseName",
]
