"""ワールド（場所移動・チェスト・採集・天気等）イベント用の観測 formatter。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    FALLBACK_ITEM_LABEL,
    FALLBACK_PLAYER_LABEL,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
    ItemStoredInChestEvent,
    ItemTakenFromChestEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum


_LOCATION_DESCRIPTION_TRUNCATE_LENGTH = 200


class WorldObservationFormatter:
    """LocationEnteredEvent / ItemTakenFromChestEvent / ResourceHarvestedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, LocationEnteredEvent):
            return self._format_location_entered(event, recipient_player_id)
        if isinstance(event, LocationExitedEvent):
            return self._format_location_exited(event, recipient_player_id)
        if isinstance(event, ItemTakenFromChestEvent):
            return self._format_item_taken_from_chest(event, recipient_player_id)
        if isinstance(event, ItemStoredInChestEvent):
            return self._format_item_stored_in_chest(event, recipient_player_id)
        if isinstance(event, ResourceHarvestedEvent):
            return self._format_resource_harvested(event, recipient_player_id)
        if isinstance(event, SpotWeatherChangedEvent):
            return self._format_spot_weather_changed(event, recipient_player_id)
        if isinstance(event, WorldObjectInteractedEvent):
            return self._format_world_object_interacted(event, recipient_player_id)
        return None

    def _interaction_type_to_prose(
        self, interaction_type: InteractionTypeEnum, data: Dict[str, Any]
    ) -> str:
        """interaction_type を LLM 向けの 5W1H 観測文に変換する。"""
        if interaction_type == InteractionTypeEnum.OPEN_CHEST:
            return "宝箱を開けました。"
        if interaction_type == InteractionTypeEnum.OPEN_DOOR:
            is_open = data.get("is_open") if isinstance(data, dict) else None
            if is_open is True:
                return "ドアを開きました。"
            if is_open is False:
                return "ドアを閉めました。"
            return "ドアを操作しました。"
        if interaction_type == InteractionTypeEnum.HARVEST:
            return "資源を採取しました。"
        if interaction_type == InteractionTypeEnum.TALK:
            return "話しかけました。"
        if interaction_type == InteractionTypeEnum.EXAMINE:
            return "調べました。"
        if interaction_type == InteractionTypeEnum.STORE_IN_CHEST:
            return "チェストに収納しました。"
        if interaction_type == InteractionTypeEnum.TAKE_FROM_CHEST:
            return "チェストから取得しました。"
        if interaction_type == InteractionTypeEnum.MONSTER_FEED:
            return "餌を与えました。"
        return "何かに触れました。"

    def _format_location_entered(
        self, event: LocationEnteredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        loc_name = event.name
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{loc_name}に着きました。"
            if event.description and event.description.strip():
                desc = event.description.strip()
                if len(desc) > _LOCATION_DESCRIPTION_TRUNCATE_LENGTH:
                    desc = desc[:_LOCATION_DESCRIPTION_TRUNCATE_LENGTH] + "…"
                prose += f" {desc}"
            structured = {
                "type": "location_entered",
                "location_name": loc_name,
                "spot_id_value": event.spot_id.value,
                "role": "self",
            }
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only"
            )
        actor_label = (
            FALLBACK_PLAYER_LABEL
            if event.player_id_value is None
            else self._context.name_resolver.player_name(PlayerId(event.player_id_value))
        )
        prose = f"{actor_label}が{loc_name}に着きました。"
        structured = {
            "type": "player_entered_location",
            "actor": actor_label,
            "location_name": loc_name,
            "spot_id_value": event.spot_id.value,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_location_exited(
        self, event: LocationExitedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ロケーションを出ました。"
        structured = {"type": "location_exited"}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_item_taken_from_chest(
        self, event: ItemTakenFromChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"チェストから{item_name}を取得しました。"
        structured = {"type": "item_taken_from_chest", "item_name": item_name}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_item_stored_in_chest(
        self, event: ItemStoredInChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"チェストに{item_name}を収納しました。"
        structured = {"type": "item_stored_in_chest", "item_name": item_name}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_resource_harvested(
        self, event: ResourceHarvestedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        parts: list[str] = []
        for entry in event.obtained_items:
            if not isinstance(entry, dict):
                continue
            spec_id_raw = entry.get("item_spec_id")
            qty = entry.get("quantity", 1)
            if spec_id_raw is None:
                parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
                continue
            try:
                spec_id_value = (
                    int(spec_id_raw) if not isinstance(spec_id_raw, int) else spec_id_raw
                )
            except (TypeError, ValueError):
                parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
                continue
            name = self._context.name_resolver.item_spec_name(spec_id_value)
            parts.append(f"{name}を{qty}個")
        if not parts:
            prose = "採集しました。"
            structured = {"type": "resource_harvested", "items": []}
        else:
            item_desc = "、".join(parts)
            prose = f"採集し、{item_desc}入手しました。"
            structured = {"type": "resource_harvested", "items": event.obtained_items}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        old_s = event.old_weather_state.weather_type.value
        new_s = event.new_weather_state.weather_type.value
        prose = f"天気が{old_s}から{new_s}に変わりました。"
        structured = {
            "type": "weather_changed",
            "old": old_s,
            "new": new_s,
            "spot_id_value": event.spot_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_world_object_interacted(
        self, event: WorldObjectInteractedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = self._interaction_type_to_prose(
            event.interaction_type, event.data or {}
        )
        if (
            event.interaction_type == InteractionTypeEnum.EXAMINE
            and event.data
        ):
            desc = (event.data.get("description") or "").strip()
            if desc:
                if len(desc) > _LOCATION_DESCRIPTION_TRUNCATE_LENGTH:
                    desc = desc[:_LOCATION_DESCRIPTION_TRUNCATE_LENGTH] + "…"
                prose += f" {desc}"
        actor_id = (
            getattr(event.actor_id, "value", event.actor_id) if event.actor_id else None
        )
        target_id = (
            getattr(event.target_id, "value", event.target_id) if event.target_id else None
        )
        structured = {
            "type": "object_interacted",
            "interaction_type": event.interaction_type.value,
            "actor_world_object_id": actor_id,
            "target_world_object_id": target_id,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )
