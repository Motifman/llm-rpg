"""戦闘（HitBox）イベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class CombatObservationFormatter:
    """HitBoxCreatedEvent / HitBoxMovedEvent / HitBoxHitRecordedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, HitBoxCreatedEvent):
            return self._format_hit_box_created(event, recipient_player_id)
        if isinstance(event, HitBoxMovedEvent):
            return self._format_hit_box_moved(event, recipient_player_id)
        if isinstance(event, HitBoxHitRecordedEvent):
            return self._format_hit_box_hit_recorded(event, recipient_player_id)
        if isinstance(event, HitBoxDeactivatedEvent):
            return self._format_hit_box_deactivated(event, recipient_player_id)
        if isinstance(event, HitBoxObstacleCollidedEvent):
            return self._format_hit_box_obstacle_collided(event, recipient_player_id)
        return None

    def _format_hit_box_created(
        self, event: HitBoxCreatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_hit_box_moved(
        self, event: HitBoxMovedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_hit_box_hit_recorded(
        self, event: HitBoxHitRecordedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "攻撃が命中しました。"
        owner_id = (
            getattr(event.owner_id, "value", event.owner_id)
            if event.owner_id
            else None
        )
        target_id = (
            getattr(event.target_id, "value", event.target_id)
            if event.target_id
            else None
        )
        structured = {
            "type": "hitbox_hit",
            "owner_world_object_id": owner_id,
            "target_world_object_id": target_id,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=True,
        )

    def _format_hit_box_deactivated(
        self, event: HitBoxDeactivatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_hit_box_obstacle_collided(
        self, event: HitBoxObstacleCollidedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None
