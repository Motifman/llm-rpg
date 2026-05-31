"""Domain event をすべて ObservationPipeline 経由で配信する EventPublisher。

Issue #227 PR 2/6 で escape_game に導入した event publisher を、PR 7 後の
chore で module-level に昇格させたもの (元は ``create_escape_game_runtime``
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
from typing import TYPE_CHECKING, Any

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_publisher import EventPublisher

if TYPE_CHECKING:  # pragma: no cover
    from demos.escape_game.escape_game_runtime import EscapeGameRuntime


logger = logging.getLogger(__name__)


class PipelineEventPublisher(EventPublisher[DomainEvent]):
    """全 DomainEvent を ObservationPipeline 経由で配信する EventPublisher。

    register_handler は no-op (per-event-type 登録は使わない)。publish /
    publish_all / publish_async_events はいずれも ``_dispatch`` に集約し、
    pipeline.run → appender.append → scheduler.maybe_schedule を実行する。

    Args:
        runtime_ref: ``EscapeGameRuntime`` への参照。``_obs_pipeline`` /
            ``_observation_appender`` / ``_observation_turn_scheduler`` を
            ここから引く。
    """

    def __init__(self, runtime_ref: "EscapeGameRuntime") -> None:
        self._runtime = runtime_ref
        # Phase E-3: side handler list。observation pipeline とは別軸で、
        # event ごとに副作用ハンドラを走らせるための登録経路。
        # (event_type, handler) のタプルで、event は handler.handle(event) で
        # 渡される。同期実行のみサポート (PlayerOutcomeRegistry 等の即時反映用)。
        self._side_handlers: list[tuple[type, Any]] = []

    def register_handler(
        self,
        event_type: Any,
        handler: Any,
        is_synchronous: bool = False,
    ) -> None:
        """Phase E-3: side handler を登録する。

        従来は no-op だったが、PlayerOutcomeRegistry の更新ハンドラを
        event-driven に組み込むため、type-filtered な dispatch list を持つよう
        拡張した。`is_synchronous` は無視 (常に同期実行)。
        """
        del is_synchronous
        if event_type is None or handler is None:
            return
        self._side_handlers.append((event_type, handler))

    def publish(self, event: DomainEvent) -> None:
        self._dispatch(event)

    def publish_all(self, events: Any) -> None:
        for event in events:
            self._dispatch(event)

    def publish_async_events(self, events: Any) -> None:
        for event in events:
            self._dispatch(event)

    def _dispatch(self, event: DomainEvent) -> None:
        # Phase E-3: side handler を先に走らせる。observation pipeline より先に
        # registry mutation を済ませることで「player downed → DEAD outcome が
        # 立った状態で観測が emit される」順序になる。
        # silent failure fix: 個別 handler の例外で observation pipeline 全体を
        # 道連れに止めないよう、handler の例外は log に残してから継続する。
        # こうしないと「最初に登録された side handler が壊れた瞬間、以降の全
        # observation が止まる」というカスケード障害になる (1 つの outcome
        # mutation bug が tick 全体の prompt 配信を止める)。
        # logger.exception で stack trace を残すので silent failure にもならない。
        for event_type, handler in self._side_handlers:
            if not isinstance(event, event_type):
                continue
            try:
                handler.handle(event)
            except Exception:
                logger.exception(
                    "side handler %s failed on event %s — continuing pipeline",
                    type(handler).__name__, type(event).__name__,
                )
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
        # tz-aware UTC で統一 (escape_game_runtime._emit_observation_directly 参照)
        now = datetime.now(timezone.utc)
        time_label = self._runtime._time_label()
        for pid, output in items:
            appender.append(pid, output, now, time_label)
            scheduler = self._runtime._observation_turn_scheduler
            if scheduler is not None:
                scheduler.maybe_schedule(pid, output)
