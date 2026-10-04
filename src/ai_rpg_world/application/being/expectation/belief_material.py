"""確定した予期を、根拠の信念への支持・反証の材料として証拠バッファに積む受け取る側。

信念は世界についての見立てで、持ち越される。誤って直すと損が大きいので、
確定した判定だけを材料にする (#1436)。暫定の外れ、期限切れ、形の判定で
外した予期、予期になっていない予期は材料にしない。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventReceiver,
)
from ai_rpg_world.application.being.expectation.likelihood_labels import (
    LIKELIHOOD_LABELS,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
    ExpectationSettled,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

# 実 run の外れ 30 件では、書いてから確定するまでの時系列は最長 1213 字だった
# (#1509)。ふだんは切らず、時系列が長くなったときだけ信念をまとめる入力を抑える。
MAX_WHAT_HAPPENED_CHARS = 1500


def expectation_outcome_text(
    content: str, likelihood: Likelihood, outcome: Outcome
) -> str:
    verdict = "当たった" if outcome is Outcome.HIT else "外れた"
    return f"{LIKELIHOOD_LABELS[likelihood]}と思っていた予期「{content}」は{verdict}。"


def settled_expectation_text(event: ExpectationSettled) -> str:
    return expectation_outcome_text(event.content, event.likelihood, event.outcome)


class ExpectationBeliefMaterialReceiver(ExpectationEventReceiver):
    """``ExpectationSettled`` を 1 件の ``BeliefEvidence`` にして積む。

    強さは本人が付けた確からしさで変える。ほぼ確実の外れだけを強い材料
    (salience=high) にし、次の固着を待たせない。それより弱い外れと当たりは
    弱い材料にする。確からしさは文にも残し、固着の LLM がどれだけ動かすかを
    読めるようにする。

    当たりは、根拠の信念が無ければ材料にしない。支える相手が無い的中を積むと、
    何もしなかっただけの当たりや、関係の無い信念への支持で水増しされる。外れは、
    根拠の信念が無くても新しく学ぶ材料として積む。

    外れには、予期を書いてから確定するまでに起きたことを付ける (#1509)。外れの
    理由はそこにしか無い。先頭から ``max_what_happened_chars`` 字に収まる行まで
    を残す。予期を書いたターンの行動の結果が先頭に来るので、後ろを切る。
    """

    def __init__(
        self,
        buffer_store: BeliefEvidenceBufferRepository,
        *,
        now_provider: Callable[[], datetime],
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        max_what_happened_chars: int,
    ) -> None:
        if not isinstance(buffer_store, BeliefEvidenceBufferRepository):
            raise TypeError("buffer_store must be BeliefEvidenceBufferRepository")
        if isinstance(max_what_happened_chars, bool) or not isinstance(
            max_what_happened_chars, int
        ):
            raise TypeError("max_what_happened_chars must be int")
        if max_what_happened_chars < 1:
            raise ValueError("max_what_happened_chars must be 1 or greater")
        self._max_what_happened_chars = max_what_happened_chars
        self._buffer_store = buffer_store
        self._now_provider = now_provider
        self._trace_recorder_provider = trace_recorder_provider

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        if not isinstance(event, ExpectationSettled):
            return
        if event.outcome is Outcome.HIT and not event.grounds.beliefs:
            self._trace(event_id, event, result="skipped", skipped_reason="no_grounding_beliefs")
            return
        what_happened, truncated = (
            _capped(event.what_happened, self._max_what_happened_chars)
            if event.outcome is Outcome.MISS
            else ((), False)
        )
        evidence = self._evidence(event_id, event, what_happened)
        appended = self._buffer_store.append_received_by_being(
            event.holder, evidence, event_id=event_id.value
        )
        self._trace(
            event_id,
            event,
            result="appended" if appended else "already_received",
            evidence=evidence,
            what_happened_truncated=truncated,
        )

    def _evidence(
        self,
        event_id: ExpectationEventId,
        event: ExpectationSettled,
        what_happened: tuple[str, ...],
    ) -> BeliefEvidence:
        miss = event.outcome is Outcome.MISS
        strong = miss and event.likelihood is Likelihood.ALMOST_CERTAIN
        return BeliefEvidence(
            evidence_id=f"belief-evidence-{event_id.value}",
            source_kind=(
                BeliefEvidenceSourceKind.PREDICTION_ERROR
                if miss
                else BeliefEvidenceSourceKind.CONFIRMATION
            ),
            # 予期はエピソードに結びつかないので、たどれる先として予期の ID を置く
            # (目的の清算が目的の ID を置くのと同じ扱い)。
            episode_ids=(event.expectation_id.value,),
            cue_signature=f"expectation:{event.outcome.value}",
            text=settled_expectation_text(event),
            salience=BELIEF_EVIDENCE_SALIENCE_HIGH if strong else BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=self._now_provider(),
            observed_turn=event.turn,
            in_context_belief_ids=event.grounds.beliefs,
            what_happened=what_happened,
        )

    def _trace(
        self,
        event_id: ExpectationEventId,
        event: ExpectationSettled,
        *,
        result: str,
        evidence: BeliefEvidence | None = None,
        skipped_reason: str | None = None,
        what_happened_truncated: bool = False,
    ) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        payload: dict[str, Any] = {
            "being_id": event.holder.value,
            "event_id": event_id.value,
            "expectation_id": event.expectation_id.value,
            "receiver": "belief_evidence",
            "outcome": event.outcome.value,
            "likelihood": event.likelihood.value,
            "result": result,
        }
        if skipped_reason is not None:
            payload["skipped_reason"] = skipped_reason
        if evidence is not None:
            payload["evidence_id"] = evidence.evidence_id
            payload["source_kind"] = evidence.source_kind.value
            payload["salience"] = evidence.salience
            payload["belief_ids"] = list(evidence.in_context_belief_ids)
            payload["what_happened_lines"] = len(evidence.what_happened)
            payload["what_happened_truncated"] = what_happened_truncated
        recorder.record(TraceEventKind.EXPECTATION_MATERIAL, **payload)


def _capped(lines: tuple[str, ...], limit: int) -> tuple[tuple[str, ...], bool]:
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) > limit:
            if not kept:
                kept.append(line[:limit])
            return tuple(kept), True
        kept.append(line)
        used += len(line)
    return tuple(kept), False


__all__ = [
    "MAX_WHAT_HAPPENED_CHARS",
    "ExpectationBeliefMaterialReceiver",
    "expectation_outcome_text",
    "settled_expectation_text",
]
