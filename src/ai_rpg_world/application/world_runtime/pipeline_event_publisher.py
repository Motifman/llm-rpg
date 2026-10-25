"""Domain event をすべて ObservationPipeline 経由で配信する EventPublisher。

Issue #227 PR 2/6 で world_runtime に導入した event publisher を、PR 7 後の
chore で module-level に昇格させたもの (元は ``create_world_runtime``
関数の内部ローカルクラス)。

設計:
- 旧 ``InMemoryEventPublisher`` の per-event-type ``register_handler`` を
  使うアプローチを廃止し、publish / publish_all / publish_async_events
  のいずれでも ``_dispatch`` に集約する単純な publisher。
- ``_dispatch`` は ObservationPipeline.run → ObservationAppender.append
  → ObservationTurnScheduler.maybe_schedule の流れで配信する。
- speech (``PlayerSpokeEvent``) と interaction (``ConnectionStateChangedEvent``
  / ``SpotObjectInteractedEvent`` / ``SpotPublicEffectObservedEvent`` 等)
  の両方でこの publisher を共有する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee, EventDispatcher

if TYPE_CHECKING:  # pragma: no cover
    from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime


logger = logging.getLogger(__name__)


class _SideHandler:
    """共通の呼び出しの口へ合わせ、失敗の記録に使う元の受け手を保持する。"""

    def __init__(self, receiver: Any) -> None:
        self.receiver = receiver

    def __call__(self, event: DomainEvent) -> None:
        self.receiver.handle(event)


class PipelineEventPublisher(EventPublisher[DomainEvent]):
    """全 DomainEvent を ObservationPipeline 経由で配信する EventPublisher。

    受け手は共通基盤の確定後へ登録し、観測より先に同期実行する。
    publish / publish_all / publish_async_events はいずれも ``_dispatch`` に
    集約し、pipeline.run → appender.append → scheduler.maybe_schedule を実行する。

    Args:
        runtime_ref: ``WorldRuntime`` への参照。``_obs_pipeline`` /
            ``_observation_appender`` / ``_observation_turn_scheduler`` を
            ここから引く。
    """

    def __init__(self, runtime_ref: WorldRuntime) -> None:
        self._runtime = runtime_ref
        self._dispatcher: EventDispatcher[None] = EventDispatcher(
            failure_observer=self._observe_side_handler_failure,
        )

    def register_handler(
        self,
        event_type: Any,
        handler: Any,
        is_synchronous: bool = False,
    ) -> None:
        """既存の登録の口を、共通基盤の確定後の同期配送へつなぐ。"""
        del is_synchronous
        if event_type is None or handler is None:
            return
        self._dispatcher.register_after_commit(
            event_type, _SideHandler(handler),
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )

    def _observe_side_handler_failure(
        self, channel: DeliveryChannel, guarantee: DeliveryGuarantee,
        event: DomainEvent, handler: object, error: Exception,
    ) -> None:
        # 静的メソッドや属性の関数でも、trace は登録した受け手の型名を残す。
        receiver = cast(_SideHandler, handler).receiver
        logger.error(
            "side handler %s failed on event %s — continuing pipeline",
            type(receiver).__name__, type(event).__name__, exc_info=error,
        )
        self._record_side_handler_failure(receiver, event, error)

    def publish(self, event: DomainEvent) -> None:
        self._dispatch(event)

    def publish_all(self, events: Any) -> None:
        for event in events:
            self._dispatch(event)

    def publish_async_events(self, events: Any) -> None:
        for event in events:
            self._dispatch(event)

    def _record_side_handler_failure(self, handler: Any, event: DomainEvent, exc: Exception) -> None:
        """side handler の失敗を trace event に落とす (best-effort、挙動は変えない)。

        ``_trace_recorder`` が runtime に無い / まだ set されていない構成では
        静かに no-op する。trace 記録自体の例外も握って pipeline を止めない
        (観測のために足したものが本体を倒すのは本末転倒なので)。
        """
        recorder = getattr(self._runtime, "_trace_recorder", None)
        if recorder is None:
            return
        try:
            from ai_rpg_world.application.trace.events import TraceEventKind

            tick_getter = getattr(self._runtime, "current_tick", None)
            tick = tick_getter() if callable(tick_getter) else None
            message = str(exc)
            if len(message) > 500:
                message = message[:500] + "…"
            # 影響対象の識別子を残す (Stage 3X の per-agent 影響分析用): どの player /
            # aggregate / event instance の副作用が失われたかを後段で集計できるように。
            aggregate_type = getattr(event, "aggregate_type", None)
            aggregate_id_raw = getattr(event, "aggregate_id", None)
            aggregate_id = getattr(aggregate_id_raw, "value", aggregate_id_raw)
            if aggregate_id is not None and not isinstance(aggregate_id, (int, str)):
                aggregate_id = str(aggregate_id)
            # aggregate が player のときだけ best-effort で player_id に昇格する。
            player_id = (
                aggregate_id
                if aggregate_type == "PlayerStatusAggregate" and isinstance(aggregate_id, int)
                else None
            )
            recorder.record(
                TraceEventKind.SIDE_HANDLER_FAILED,
                tick=getattr(tick, "value", tick),
                player_id=player_id,
                handler=type(handler).__name__,
                event_type=type(event).__name__,
                event_id=getattr(event, "event_id", None),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                error_type=type(exc).__name__,
                error_message=message,
            )
        except Exception:
            logger.warning(
                "failed to record SIDE_HANDLER_FAILED trace for handler=%s event=%s",
                type(handler).__name__, type(event).__name__,
                exc_info=True,
            )

    def _dispatch(self, event: DomainEvent) -> None:
        # 公開SNSの受信は専用の確定境界で記録する。旧formatterへ同じ通知を
        # 二重に流すと全文・起床が重複するため、ここで一本化する。
        from ai_rpg_world.domain.sns.event import SnsContentLikedEvent, SnsUserFollowedEvent
        public_sns = getattr(self._runtime, "_public_sns_command_service", None)
        if public_sns is not None and isinstance(event, (SnsContentLikedEvent, SnsUserFollowedEvent)):
            public_sns.record_event(event)
            return
        # 観測を作る前に、確定後の受け手の反映を済ませる。直接発行も同じ口を通す。
        self._dispatcher.handoff([event])
        items = self._runtime._obs_pipeline.run(event)
        if not items:
            return
        # PR 7 review HIGH 1: 本番 assert は不可 (python -O で無効化)。
        # 構築途中で publisher 経由イベントが入った場合に備え if-return で
        # 静かに skip する。
        appender = self._runtime._observation_appender
        if appender is None:
            logger.debug(
                "PipelineEventPublisher: observation_appender is not yet set, "
                "skipping event=%s",
                type(event).__name__,
            )
            return
        # tz-aware UTC で統一 (world_runtime._emit_observation_directly 参照)
        now = datetime.now(timezone.utc)
        time_label = self._runtime._time_label()
        for pid, output in items:
            if not appender.append(pid, output, now, time_label):
                continue
            scheduler = self._runtime._observation_turn_scheduler
            if scheduler is not None:
                scheduler.maybe_schedule(pid, output)
