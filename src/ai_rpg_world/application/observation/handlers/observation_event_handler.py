"""
観測用イベントハンドラ。
ドメインイベントを購読し、パイプライン経由で観測を蓄積する。
非同期で実行する（別 UoW）。副作用（buffer append、cancel_movement、schedule_turn）は専用サービスに委譲。
"""

import logging
from typing import Any, Callable

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.observation.services.movement_interruption_service import (
    MovementInterruptionService,
)
from ai_rpg_world.application.observation.services.observation_appender import ObservationAppender
from ai_rpg_world.application.observation.services.observation_pipeline import ObservationPipeline
from ai_rpg_world.application.observation.services.observation_timestamp_resolver import (
    ObservationTimestampResolver,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory


class ObservationEventHandler(EventHandler[Any]):
    """
    観測対象のドメインイベントを購読し、
    Pipeline → Appender → MovementInterruption / TurnScheduler の流れで処理する。
    別 UoW 内で pipeline を組み立て・実行するだけに責務を縮小。
    """

    def __init__(
        self,
        pipeline: ObservationPipeline,
        appender: ObservationAppender,
        timestamp_resolver: ObservationTimestampResolver,
        movement_interruption: MovementInterruptionService,
        turn_scheduler: ObservationTurnScheduler,
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> None:
        self._pipeline = pipeline
        self._appender = appender
        self._timestamp_resolver = timestamp_resolver
        self._movement_interruption = movement_interruption
        self._turn_scheduler = turn_scheduler
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: Any) -> None:
        try:
            self._execute_in_separate_transaction(
                lambda: self._handle_impl(event),
                context={"handler": "ObservationEventHandler", "event_type": type(event).__name__},
            )
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in ObservationEventHandler: %s",
                e,
                extra={"event_type": type(event).__name__},
            )
            raise SystemErrorException(
                f"Observation handling failed: {e}",
                original_exception=e,
            ) from e

    def _execute_in_separate_transaction(self, operation: Callable[[], None], context: dict) -> None:
        """別トランザクションで操作を実行。非同期ハンドラ方針に従う。"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                context.get("handler", "unknown"),
                e,
                extra=context,
            )
            raise SystemErrorException(
                f"Observation event handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: Any) -> None:
        items = self._pipeline.run(event)
        occurred_at = self._timestamp_resolver.resolve_occurred_at(event)
        game_time_label = self._timestamp_resolver.resolve_game_time_label(event)

        for player_id, output in items:
            self._appender.append(player_id, output, occurred_at, game_time_label)
            self._movement_interruption.maybe_cancel(player_id, output)
            self._turn_scheduler.maybe_schedule(player_id, output)
