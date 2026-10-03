"""確定した予期の当否を、それを持ったときに思い出していたエピソードへ返す受け取る側。

当たったなら、そのエピソードは思い出す価値があったとして役に立った回数を 1 増やす。
外れたなら、そのエピソードの想起にずれを書き添え、再解釈が「思い出したのに
外れた」として読み直せるようにする。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
    """``ExpectationSettled`` の当否を ``episodes_in_mind`` へ返す。

    役に立った回数の記録先と想起の記録先は、それぞれの記憶の機能が有効なときだけ
    渡される。無い側に届いた確定は、書かずに理由を trace に残す。
    """

    def __init__(
        self,
        *,
        success_store: IEpisodicRecallSuccessStore | None,
        recall_buffer_store: EpisodicRecallBufferRepository | None,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        if success_store is not None and not isinstance(
            success_store, IEpisodicRecallSuccessStore
        ):
            raise TypeError("success_store must implement IEpisodicRecallSuccessStore")
        if recall_buffer_store is not None and not isinstance(
            recall_buffer_store, EpisodicRecallBufferRepository
        ):
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
            self._credit_hit(event_id, event)
        else:
            self._stamp_miss(event_id, event)

    def _credit_hit(self, event_id: ExpectationEventId, event: ExpectationSettled) -> None:
        if self._success_store is None:
            self._trace(event_id, event, result="skipped", skipped_reason="recall_success_store_unwired")
            return
        recorded = self._success_store.record_hits_received_by_being(
            event.holder, event.episodes_in_mind, event_id=event_id.value
        )
        self._trace(
            event_id,
            event,
            result="appended" if recorded else "already_received",
            credit="hit_count",
        )

    def _stamp_miss(self, event_id: ExpectationEventId, event: ExpectationSettled) -> None:
        if self._recall_buffer_store is None:
            self._trace(event_id, event, result="skipped", skipped_reason="recall_buffer_unwired")
            return
        stamped = self._recall_buffer_store.stamp_prediction_outcome_for_episodes_by_being(
            event.holder,
            event.episodes_in_mind,
            settled_expectation_text(event),
            event_id=event_id.value,
        )
        # 想起が再解釈で処理済みなら 0 件になる。受け取り済みと区別して件数を残す。
        self._trace(
            event_id,
            event,
            result="already_received" if stamped is None else "appended",
            credit="miss_stamp",
            stamped_recalls=stamped,
        )

    def _trace(
        self,
        event_id: ExpectationEventId,
        event: ExpectationSettled,
        *,
        result: str,
        credit: str | None = None,
        skipped_reason: str | None = None,
        stamped_recalls: int | None = None,
    ) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        payload: dict[str, Any] = {
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
        if stamped_recalls is not None:
            payload["stamped_recalls"] = stamped_recalls
        recorder.record(TraceEventKind.EXPECTATION_MATERIAL, **payload)


__all__ = ["ExpectationRecallCreditReceiver"]
