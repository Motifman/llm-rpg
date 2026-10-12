"""名前の重なりで当たらなかった品名を、相手の所持品から意味で選び直す (#1641)。

対象名の救済 (target_label_rescue.py) と同じ問いを、人を対象にした操作の
引数 ``item`` に向ける。候補は相手の所持品で、当人には見えていない。

## 「どれでもない」も確信を問う

対象名の救済は、確信が足りなければ従来どおり失敗させればよかった。品名では
失敗の文が「相手はそれを持っていない」になり、持っている相手を嘘つきにする。
だから「該当なし」も確率と確信が下限に届いたときだけ言い切り、届かなければ
見分けられなかったと返す (design_decisions D1641)。

閾値は対象名と同じ ``typed_judgment_target_label_min_confidence`` (既定 0.85)。
どちらも世界に在る物へ名前を当てる判断で、誤ると別の物を動かす。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
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

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.world_graph.target_item_name_resolution import ItemNameRescueAnswer

logger = logging.getLogger(__name__)

NO_MATCH_OPTION = "__no_match__"
QUESTION_NAME = "target_item_name_rescue"


class TargetItemNameRescue:
    def __init__(self, *, port: ITypedJudgmentPort, min_confidence: float) -> None:
        if not isinstance(min_confidence, (int, float)):
            raise TypeError("min_confidence must be a number")
        if not 0.0 < float(min_confidence) <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        self.min_confidence = float(min_confidence)
        self._resolver = SemanticResolver(
            backend=_Backend(port), policy=_Policy(self.min_confidence)
        )

    def rescue(
        self, written: str, *, candidates: Mapping[str, str], action_name: str
    ) -> ItemNameRescueAnswer:
        state = {
            "written_item_name": written,
            "action_name": action_name,
            "candidates": dict(candidates),
        }
        try:
            result = self._resolver.resolve(
                value=written,
                candidates=[Candidate(name, description) for name, description in candidates.items()],
                context=state,
            )
        except BackendError as exc:
            logger.warning("target item name rescue unavailable: %s", exc)
            return ItemNameRescueAnswer(
                chosen=None, accepted=False, confident_no_match=False,
                payload=self._payload(written, None, None, accepted=False, unavailable_reason=exc.code),
            )
        assert result.judgment is not None
        answer = result.judgment.evidence
        chosen = result.judgment.value
        accepted = isinstance(result, Resolved)
        return ItemNameRescueAnswer(
            chosen=chosen,
            accepted=accepted,
            confident_no_match=chosen is None and _confident(answer, self.min_confidence),
            payload=self._payload(written, chosen, answer, accepted=accepted),
        )

    def _payload(
        self,
        written: str,
        chosen: str | None,
        answer: JudgmentResult | None,
        *,
        accepted: bool,
        unavailable_reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "question": QUESTION_NAME,
            "argument": "item",
            "original": written,
            "replaced_with": chosen if accepted else None,
            "chosen": chosen,
            "probability": answer.probabilities.get(str(answer.value)) if answer else None,
            "confidence": answer.confidence if answer else None,
            "min_confidence": self.min_confidence,
            "accepted": accepted,
            "latency_ms": answer.latency_ms if answer else None,
            "source": answer.source.value if answer else None,
            "unavailable_reason": unavailable_reason,
        }


def _confident(answer: JudgmentResult, minimum: float) -> bool:
    probability = answer.probabilities.get(str(answer.value))
    return (
        probability is not None
        and probability >= minimum
        and (answer.confidence is None or answer.confidence >= minimum)
    )


class _Backend:
    def __init__(self, port: ITypedJudgmentPort) -> None:
        self._port = port

    def judge(self, request: ResolutionRequest) -> Judgment[JudgmentResult]:
        options = {c.value: c.description for c in request.candidates}
        if NO_MATCH_OPTION in options:
            raise BackendError("item name collides with the no-match option")
        question = ChoiceQuestion(
            instructions=(
                "書かれた品の名前 written_item_name は、相手の持ち物のどれを指しているか。"
                f"どれでもなければ {NO_MATCH_OPTION} を選ぶ。"
            ),
            options={**options, NO_MATCH_OPTION: "相手の持ち物のどれにも当たらない"},
        )
        try:
            answers = self._port.judge(request.context, {QUESTION_NAME: question})
        except TypedJudgmentUnavailableException as exc:
            raise BackendError(str(exc), code=exc.error_code) from exc
        answer = answers.get(QUESTION_NAME)
        if answer is None:
            raise BackendError("target item name rescue answer missing", code="ANSWER_MISSING")
        chosen = str(answer.value)
        return Judgment(
            value=None if chosen == NO_MATCH_OPTION else chosen,
            evidence=answer, backend=answer.source.value, model="", latency_ms=answer.latency_ms,
        )


class _Policy:
    def __init__(self, minimum: float) -> None:
        self._minimum = minimum

    def assess(self, judgment: Judgment[JudgmentResult]) -> Assessment:
        accepted = _confident(judgment.evidence, self._minimum)
        return Assessment(
            reason="accepted" if accepted else "below_threshold",
            thresholds={"min_probability": self._minimum, "min_confidence": self._minimum},
        )


__all__ = ["NO_MATCH_OPTION", "QUESTION_NAME", "TargetItemNameRescue"]
