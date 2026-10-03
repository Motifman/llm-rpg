"""確定した予期の当否を、それを持ったときに思い出していたエピソードへ返す受け取る側。

当たったなら、そのエピソードは思い出す価値があったとして役に立った回数を 1 増やす。
外れたなら、そのエピソードの想起にずれを書き添え、再解釈が「思い出したのに
外れた」として読み直せるようにする。
"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.being.expectation.belief_material import (
    settled_expectation_text,
)
from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventReceiver,
)
from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
    IEpisodicRecallSuccessStore,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
    EpisodicRecallBufferRepository,
)
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


class ExpectationRecallCreditReceiver(ExpectationEventReceiver):
    """``ExpectationSettled`` の当否を ``episodes_in_mind`` へ返す。"""

    def __init__(
        self,
        *,
        success_store: IEpisodicRecallSuccessStore,
        recall_buffer_store: EpisodicRecallBufferRepository,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        if not isinstance(success_store, IEpisodicRecallSuccessStore):
            raise TypeError("success_store must implement IEpisodicRecallSuccessStore")
        if not isinstance(recall_buffer_store, EpisodicRecallBufferRepository):
            raise TypeError("recall_buffer_store must be EpisodicRecallBufferRepository")
        self._success_store = success_store
        self._recall_buffer_store = recall_buffer_store
        self._trace_recorder_provider = trace_recorder_provider

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        if not isinstance(event, ExpectationSettled):
            return
        if not event.episodes_in_mind:
            self._trace(event_id, event, result="skipped", skipped_reason="no_episodes_in_mind")
            return
        if event.outcome is Outcome.HIT:
            credit = "hit_count"
            applied = self._success_store.record_hits_received_by_being(
                event.holder, event.episodes_in_mind, event_id=event_id.value
            )
        else:
            credit = "miss_stamp"
            applied = self._recall_buffer_store.stamp_prediction_outcome_for_episodes_by_being(
                event.holder,
                event.episodes_in_mind,
                settled_expectation_text(event),
                event_id=event_id.value,
            )
        self._trace(
            event_id,
            event,
            result="appended" if applied else "already_received",
            credit=credit,
        )

    def _trace(
        self,
        event_id: ExpectationEventId,
        event: ExpectationSettled,
        *,
        result: str,
        credit: str | None = None,
        skipped_reason: str | None = None,
    ) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        payload: dict[str, object] = {
            "being_id": event.holder.value,
            "event_id": event_id.value,
            "expectation_id": event.expectation_id.value,
            "receiver": "recall_credit",
            "outcome": event.outcome.value,
            "likelihood": event.likelihood.value,
            "result": result,
        }
        if skipped_reason is not None:
            payload["skipped_reason"] = skipped_reason
        if credit is not None:
            payload["credit"] = credit
            payload["episode_ids"] = list(event.episodes_in_mind)
        recorder.record(TraceEventKind.EXPECTATION_MATERIAL, **payload)


__all__ = ["ExpectationRecallCreditReceiver"]
