"""エンティティ移動・探索・prepared action の formatter。

SpotGraph の event のうち「プレイヤー本人の移動/操作」に相当する物を扱う。
共通: 行為者本人は除外 (ツール結果で代替)、同スポット他プレイヤーには
social として届ける。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._spot_graph_formatter_helpers import (
    _SpotGraphFormatterBase,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
    SpotExploredEvent,
    SpotPlayerPreparedActionEvent,
)


class SpotGraphMovementHandler(_SpotGraphFormatterBase):
    """移動系イベントの formatter。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, EntityEnteredSpotEvent):
            return self._format_entity_entered(event, recipient_player_id)
        if isinstance(event, EntityLeftSpotEvent):
            return self._format_entity_left(event, recipient_player_id)
        if isinstance(event, SpotExploredEvent):
            return self._format_explored(event, recipient_player_id)
        if isinstance(event, SpotPlayerPreparedActionEvent):
            return self._format_prepared_action(event, recipient_player_id)
        return None

    def _format_entity_entered(
        self, event: EntityEnteredSpotEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        spot = self._resolve_spot_name(event.spot_id)
        prose = f"{actor}が{spot}にやってきた。"
        structured = {
            "type": "entity_entered_spot",
            "actor": actor,
            "spot_name": spot,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_entity_left(
        self, event: EntityLeftSpotEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = f"{actor}がこのスポットを去った。"
        structured = {
            "type": "entity_left_spot",
            "actor": actor,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_explored(
        self, event: SpotExploredEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = f"{actor}が周囲を探索している。"
        structured = {
            "type": "spot_explored",
            "actor": actor,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_prepared_action(
        self, event: SpotPlayerPreparedActionEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        # アクター本人は自身の prepare 操作結果をツール側で受け取るため除外。
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = event.observation_message
        structured = {
            "type": "spot_player_prepared_action",
            "actor": actor,
            "action_id": event.action_id,
            "group_id": event.group_id,
            "message": event.observation_message,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social",
        )
