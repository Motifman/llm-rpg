"""採集イベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)


class HarvestObservationFormatter:
    """HarvestStartedEvent / HarvestCancelledEvent / HarvestCompletedEvent を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, HarvestStartedEvent):
            return self._format_harvest_started(event, recipient_player_id)
        if isinstance(event, HarvestCancelledEvent):
            return self._format_harvest_cancelled(event, recipient_player_id)
        if isinstance(event, HarvestCompletedEvent):
            return self._format_harvest_completed(event, recipient_player_id)
        return None

    def _format_harvest_started(
        self, event: HarvestStartedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "採集を開始しました。"
        finish_tick = int(getattr(event.finish_tick, "value", event.finish_tick))
        structured = {"type": "harvest_started", "finish_tick": finish_tick}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
        )

    def _format_harvest_cancelled(
        self, event: HarvestCancelledEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"採集を中断しました（理由: {event.reason}）。"
        structured = {"type": "harvest_cancelled", "reason": event.reason}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
        )

    def _format_harvest_completed(
        self, event: HarvestCompletedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "採集が完了しました。"
        structured = {"type": "harvest_completed"}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
        )
