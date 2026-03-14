"""追跡（Pursuit）イベント用の観測 formatter。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)


class PursuitObservationFormatter:
    """PursuitStartedEvent / PursuitUpdatedEvent / PursuitFailedEvent / PursuitCancelledEvent を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, PursuitStartedEvent):
            return self._format_pursuit_started(event, recipient_player_id)
        if isinstance(event, PursuitUpdatedEvent):
            return self._format_pursuit_updated(event, recipient_player_id)
        if isinstance(event, PursuitFailedEvent):
            return self._format_pursuit_failed(event, recipient_player_id)
        if isinstance(event, PursuitCancelledEvent):
            return self._format_pursuit_cancelled(event, recipient_player_id)
        return None

    def _base_pursuit_structured(
        self,
        *,
        event_type: str,
        actor_id: Any,
        target_id: Any,
        pursuit_status_after_event: str,
        interruption_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        actor_id_value = getattr(actor_id, "value", actor_id)
        target_id_value = getattr(target_id, "value", target_id)
        structured: Dict[str, Any] = {
            "type": event_type,
            "event_type": event_type,
            "actor_id": actor_id_value,
            "target_id": target_id_value,
            "actor_world_object_id": actor_id_value,
            "target_world_object_id": target_id_value,
            "pursuit_status_after_event": pursuit_status_after_event,
        }
        if interruption_scope is not None:
            structured["interruption_scope"] = interruption_scope
        return structured

    def _serialize_pursuit_coordinate(self, coordinate: Any) -> Optional[Dict[str, int]]:
        if coordinate is None:
            return None
        return {
            "x": int(getattr(coordinate, "x", 0)),
            "y": int(getattr(coordinate, "y", 0)),
            "z": int(getattr(coordinate, "z", 0)),
        }

    def _serialize_last_known_state(self, last_known: Any) -> Optional[Dict[str, Any]]:
        if last_known is None:
            return None
        return {
            "target_id": getattr(getattr(last_known, "target_id", None), "value", None),
            "spot_id_value": getattr(getattr(last_known, "spot_id", None), "value", None),
            "coordinate": self._serialize_pursuit_coordinate(
                getattr(last_known, "coordinate", None)
            ),
            "observed_at_tick": getattr(
                getattr(last_known, "observed_at_tick", None), "value", getattr(last_known, "observed_at_tick", None)
            ),
        }

    def _serialize_target_snapshot(self, target_snapshot: Any) -> Optional[Dict[str, Any]]:
        if target_snapshot is None:
            return None
        return {
            "target_id": getattr(getattr(target_snapshot, "target_id", None), "value", None),
            "spot_id_value": getattr(getattr(target_snapshot, "spot_id", None), "value", None),
            "coordinate": self._serialize_pursuit_coordinate(
                getattr(target_snapshot, "coordinate", None)
            ),
        }

    def _format_pursuit_started(
        self,
        event: PursuitStartedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "対象の追跡を開始しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_started",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="active",
        )
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(
            event.last_known.spot_id, "value", event.last_known.spot_id
        )
        structured["target_snapshot"] = self._serialize_target_snapshot(event.target_snapshot)
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_pursuit_updated(
        self,
        event: PursuitUpdatedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "対象の追跡状況を更新しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_updated",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="active",
        )
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(
            event.last_known.spot_id, "value", event.last_known.spot_id
        )
        structured["target_snapshot"] = self._serialize_target_snapshot(
            event.target_snapshot
        )
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_pursuit_failed(
        self,
        event: PursuitFailedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "追跡に失敗しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_failed",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="ended",
            interruption_scope="pursuit",
        )
        structured["failure_reason"] = event.failure_reason.value
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(
            event.last_known.spot_id, "value", event.last_known.spot_id
        )
        structured["target_snapshot"] = self._serialize_target_snapshot(
            event.target_snapshot
        )
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_pursuit_cancelled(
        self,
        event: PursuitCancelledEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "追跡を中断しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_cancelled",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="ended",
            interruption_scope="pursuit",
        )
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(
            event.last_known.spot_id, "value", event.last_known.spot_id
        )
        structured["target_snapshot"] = self._serialize_target_snapshot(
            event.target_snapshot
        )
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )
