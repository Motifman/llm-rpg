"""候補に当たらなかった対象の名前を、いま選べる候補から意味で選び直す。

行動名の救済 (action_name_rescue.py、#1321) と同じ問いを、名前で対象を引く
全ツール (interact / use_item / drop_item / pickup_item / give_item / travel_to)
の名前引数に向ける。最初は ``interact`` の ``target_label`` だけだった。過去 65 run の ``INVALID_TARGET_LABEL`` 212 件のうち、
候補があった 70 件を Jev に問うと、正しく寄せたのが 5 件 (「East Shrine」→
「東の祭壇」、「东の祭壇」→「東の祭壇」、「漂着物」→「波が運んだ漂着物」、
「貝」→「貝の岩棚」)、正しく「該当なし」と言ったのが 58 件だった
(scripts/jev_target_label_rescue_demo.py)。

## 問わない場面

- 名前が候補に当たった (写し崩れの正規化を含む): 問う必要がない
- 候補集合が空: 選び直す先が無い
- 別の種別に在る・同名が複数: 名前の問題ではなく、決定的に分かる (target_lookup)

## 「該当なし」を必ず選択肢に入れる

「大型カニ」に対して「貝の岩棚」しか無いとき、寄せてはいけない。世界に無い
ものを一番近いものに化けさせない。

## 閾値は行動名より高く置く

正しく寄せた 5 件の最小は確率 0.93 / 確信 0.89。誤った寄せ (手持ちの品を
対象物の一覧から選んだ型、いまは種別の解決で構造的に消えている) は 0.8 台
だった。既定 0.85。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from semantic_resolver import (
    Assessment,
    BackendError,
    Candidate,
    Judgment,
    ResolutionRequest,
    Resolved,
    SemanticResolver,
)

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_lookup import KIND_LABEL

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto

logger = logging.getLogger(__name__)

NO_MATCH_OPTION = "__no_match__"
QUESTION_NAME = "target_label_rescue"


@dataclass(frozen=True)
class TargetLabelJudgment:
    """対象名の選び直しを問うた結果。採らなかった判断も残す。"""

    chosen: str | None
    probability: float | None
    confidence: float | None
    min_confidence: float
    accepted: bool
    latency_ms: float | None = None
    source: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class TargetLabelResolution:
    """選び直しの結果。``target`` が None なら従来どおり失敗させる。"""

    original: str
    target: ToolRuntimeTargetDto | None
    judgment: TargetLabelJudgment | None
    tool: str = ""
    argument: str = ""

    def payload(self) -> dict[str, Any] | None:
        """trace と結果文に要る値。判断を問っていなければ None。

        ``tool`` と ``argument`` が無いと、trace で「どのツールのどの名前を
        選び直したか」が分からない。1 ツールなら不要だったが、5 ツールになる。
        """
        if self.judgment is None:
            return None
        j = self.judgment
        return {
            "tool": self.tool,
            "argument": self.argument,
            "original": self.original,
            "replaced_with": self.target.display_name if (j.accepted and self.target) else None,
            "chosen": j.chosen,
            "probability": j.probability,
            "confidence": j.confidence,
            "min_confidence": j.min_confidence,
            "accepted": j.accepted,
            "latency_ms": j.latency_ms,
            "source": j.source,
            "unavailable_reason": j.unavailable_reason,
        }


class TargetLabelRescue:
    """候補に当たらなかった対象の名前を、意味で選び直す。"""

    def __init__(self, *, port: ITypedJudgmentPort, min_confidence: float) -> None:
        if not isinstance(min_confidence, (int, float)):
            raise TypeError("min_confidence must be a number")
        if not 0.0 < float(min_confidence) <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        self._resolver = SemanticResolver(
            backend=_TargetLabelBackend(port),
            policy=_TargetLabelPolicy(float(min_confidence)),
        )
        self.min_confidence = float(min_confidence)

    def rescue(
        self,
        written: str,
        *,
        candidates: Sequence[ToolRuntimeTargetDto],
        tool: str,
        inner_thought: str | None,
        argument: str = "",
    ) -> TargetLabelResolution:
        """当たらなかった名前を候補から選び直す。確信が足りなければ target は None。

        ``argument`` は当人向けの引数名 (「渡す相手の名前」など)。Jev に「何として
        書かれた名前か」を伝え、trace で判断を引き分ける。
        """
        written = (written or "").strip()
        by_name = _by_display_name(candidates)
        if not written or not by_name:
            return TargetLabelResolution(original=written, target=None, judgment=None, tool=tool, argument=argument)
        state = _state(written, tool, argument, by_name, inner_thought)
        try:
            result = self._resolver.resolve(
                value=written,
                candidates=[Candidate(name, _hint(t)) for name, t in by_name.items()],
                context=state,
            )
        except BackendError as exc:
            logger.warning("target label rescue unavailable: %s", exc)
            return TargetLabelResolution(
                original=written,
                target=None,
                judgment=TargetLabelJudgment(
                    chosen=None, probability=None, confidence=None,
                    min_confidence=self.min_confidence, accepted=False,
                    unavailable_reason=exc.code,
                ),
                tool=tool,
                argument=argument,
            )
        assert result.judgment is not None
        answer = result.judgment.evidence
        chosen = result.judgment.value
        accepted = isinstance(result, Resolved)
        target = by_name.get(str(result.value)) if isinstance(result, Resolved) else None
        judgment = TargetLabelJudgment(
            chosen=chosen,
            probability=answer.probabilities.get(str(answer.value)),
            confidence=answer.confidence,
            min_confidence=self.min_confidence,
            accepted=accepted,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )
        return TargetLabelResolution(original=written, target=target, judgment=judgment, tool=tool, argument=argument)


class _TargetLabelBackend:
    def __init__(self, port: ITypedJudgmentPort) -> None:
        self._port = port

    def judge(self, request: ResolutionRequest) -> Judgment[JudgmentResult]:
        options = {c.value: c.description for c in request.candidates}
        if NO_MATCH_OPTION in options:
            raise BackendError("target name collides with the no-match option")
        question = ChoiceQuestion(
            instructions=(
                "書かれた対象の名前 written_target_name は、いま選べる候補のどれを"
                f"指しているか。どれでもなければ {NO_MATCH_OPTION} を選ぶ。"
            ),
            options={**options, NO_MATCH_OPTION: "一覧のどれにも当たらない"},
        )
        try:
            answers = self._port.judge(request.context, {QUESTION_NAME: question})
        except TypedJudgmentUnavailableException as exc:
            raise BackendError(str(exc), code=exc.error_code) from exc
        answer = answers.get(QUESTION_NAME)
        if answer is None:
            raise BackendError("target label rescue answer missing", code="ANSWER_MISSING")
        chosen = str(answer.value)
        return Judgment(
            value=None if chosen == NO_MATCH_OPTION else chosen,
            evidence=answer, backend=answer.source.value, model="", latency_ms=answer.latency_ms,
        )


class _TargetLabelPolicy:
    def __init__(self, minimum: float) -> None:
        self._minimum = minimum

    def assess(self, judgment: Judgment[JudgmentResult]) -> Assessment:
        answer = judgment.evidence
        probability = answer.probabilities.get(str(answer.value))
        accepted = (
            probability is not None
            and probability >= self._minimum
            and (answer.confidence is None or answer.confidence >= self._minimum)
        )
        return Assessment(
            reason="accepted" if accepted else "below_threshold",
            thresholds={"min_probability": self._minimum, "min_confidence": self._minimum},
        )


def _by_display_name(candidates: Sequence[ToolRuntimeTargetDto]) -> dict[str, ToolRuntimeTargetDto]:
    out: dict[str, ToolRuntimeTargetDto] = {}
    for t in candidates:
        name = (t.display_name or "").strip()
        if name and name not in out:
            out[name] = t
    return out


def _hint(target: ToolRuntimeTargetDto) -> str:
    """候補の説明。種別と、持っている操作の意味ラベル。整数 ID は入れない。"""
    parts = [KIND_LABEL.get(target.kind, target.kind)]
    labels = [label for _, label in (target.interaction_labels or ()) if label]
    if labels:
        parts.append("できること: " + " / ".join(labels[:4]))
    return "。".join(parts)


def _state(
    written: str,
    tool: str,
    argument: str,
    by_name: Mapping[str, ToolRuntimeTargetDto],
    inner_thought: str | None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "written_target_name": written,
        "tool": tool,
        "candidates": {name: _hint(t) for name, t in by_name.items()},
    }
    if argument:
        state["argument"] = argument
    thought = (inner_thought or "").strip()
    if thought:
        state["inner_thought"] = thought
    return state


__all__ = ["NO_MATCH_OPTION", "QUESTION_NAME", "TargetLabelJudgment", "TargetLabelRescue", "TargetLabelResolution"]
