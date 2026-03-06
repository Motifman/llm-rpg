"""観測テキスト（プローズ＋構造化）を生成するフォーマッタ実装"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import IObservationFormatter
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLocationChangedEvent,
    PlayerDownedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository


# 名前解決に失敗したときのラベル（ID を露出しない）
FALLBACK_SPOT_LABEL = "不明なスポット"
FALLBACK_PLAYER_LABEL = "不明なプレイヤー"
FALLBACK_ITEM_LABEL = "何かのアイテム"


class ObservationFormatter(IObservationFormatter):
    """
    イベント＋配信先を観測テキスト（プローズ文と構造化 dict）に変換する。
    仕様の「観測内容（例）」に基づく。名前解決は任意のリポジトリで行う。
    """

    def __init__(
        self,
        spot_repository: Optional["SpotRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
        item_spec_repository: Optional["ItemSpecRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
    ) -> None:
        self._spot_repository = spot_repository
        self._player_profile_repository = player_profile_repository
        self._item_spec_repository = item_spec_repository
        self._item_repository = item_repository

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
        attention_level: Optional[AttentionLevel] = None,
    ) -> Optional[ObservationOutput]:
        """指定プレイヤー向けの観測出力を生成。attention_level に応じてスキップする。"""
        output: Optional[ObservationOutput] = None
        if isinstance(event, GatewayTriggeredEvent):
            output = self._format_gateway_triggered(event, recipient_player_id)
        elif isinstance(event, LocationEnteredEvent):
            output = self._format_location_entered(event, recipient_player_id)
        elif isinstance(event, LocationExitedEvent):
            output = self._format_location_exited(event, recipient_player_id)
        elif isinstance(event, PlayerLocationChangedEvent):
            output = self._format_player_location_changed(event, recipient_player_id)
        elif isinstance(event, PlayerDownedEvent):
            output = self._format_player_downed(event, recipient_player_id)
        elif isinstance(event, PlayerRevivedEvent):
            output = self._format_player_revived(event, recipient_player_id)
        elif isinstance(event, PlayerLevelUpEvent):
            output = self._format_player_level_up(event, recipient_player_id)
        elif isinstance(event, PlayerGoldEarnedEvent):
            output = self._format_player_gold_earned(event, recipient_player_id)
        elif isinstance(event, PlayerGoldPaidEvent):
            output = self._format_player_gold_paid(event, recipient_player_id)
        elif isinstance(event, ItemTakenFromChestEvent):
            output = self._format_item_taken_from_chest(event, recipient_player_id)
        elif isinstance(event, ItemStoredInChestEvent):
            output = self._format_item_stored_in_chest(event, recipient_player_id)
        elif isinstance(event, ResourceHarvestedEvent):
            output = self._format_resource_harvested(event, recipient_player_id)
        elif isinstance(event, SpotWeatherChangedEvent):
            output = self._format_spot_weather_changed(event, recipient_player_id)
        elif isinstance(event, WorldObjectInteractedEvent):
            output = self._format_world_object_interacted(event, recipient_player_id)
        elif isinstance(event, ItemAddedToInventoryEvent):
            output = self._format_item_added_to_inventory(event, recipient_player_id)
        elif isinstance(event, ItemDroppedFromInventoryEvent):
            output = self._format_item_dropped(event, recipient_player_id)
        elif isinstance(event, ItemEquippedEvent):
            output = self._format_item_equipped(event, recipient_player_id)
        elif isinstance(event, ItemUnequippedEvent):
            output = self._format_item_unequipped(event, recipient_player_id)
        elif isinstance(event, InventorySlotOverflowEvent):
            output = self._format_inventory_slot_overflow(event, recipient_player_id)

        if output is None:
            return None
        # attention_level に応じたフィルタ（FULL または未指定はそのまま）
        if attention_level is None or attention_level == AttentionLevel.FULL:
            return output
        if attention_level == AttentionLevel.FILTER_SOCIAL:
            if output.observation_category == "social":
                return None
        if attention_level == AttentionLevel.IGNORE:
            if output.observation_category != "self_only":
                return None
        return output

    def _spot_name(self, spot_id: SpotId) -> str:
        if self._spot_repository:
            spot = self._spot_repository.find_by_id(spot_id)
            if spot:
                return spot.name
        return FALLBACK_SPOT_LABEL

    def _player_name(self, player_id: PlayerId) -> str:
        if self._player_profile_repository:
            profile = self._player_profile_repository.find_by_id(player_id)
            if profile and hasattr(profile, "name"):
                return profile.name.value
        return FALLBACK_PLAYER_LABEL

    def _item_spec_name(self, item_spec_id_value: int) -> str:
        if self._item_spec_repository is None:
            return FALLBACK_ITEM_LABEL
        try:
            from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
            spec_id = ItemSpecId(item_spec_id_value)
        except Exception:
            return FALLBACK_ITEM_LABEL
        spec = self._item_spec_repository.find_by_id(spec_id)
        if spec is not None:
            return spec.name
        return FALLBACK_ITEM_LABEL

    def _item_instance_name(self, item_instance_id: Any) -> str:
        if self._item_repository is None:
            return FALLBACK_ITEM_LABEL
        agg = self._item_repository.find_by_id(item_instance_id)
        if agg is not None:
            return agg.item_spec.name
        return FALLBACK_ITEM_LABEL

    def _format_gateway_triggered(
        self, event: GatewayTriggeredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        target_name = self._spot_name(event.target_spot_id)
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{target_name}に到着しました。"
            structured = {"type": "gateway_arrival", "spot_name": target_name, "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_label = FALLBACK_PLAYER_LABEL if event.player_id_value is None else self._player_name(PlayerId(event.player_id_value))
        prose = f"{actor_label}がこのスポットにやってきました。"
        structured = {"type": "player_entered_spot", "actor": actor_label, "spot_name": target_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social", causes_interrupt=True
        )

    def _format_location_entered(
        self, event: LocationEnteredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        loc_name = event.name
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{loc_name}に着きました。"
            structured = {"type": "location_entered", "location_name": loc_name, "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_label = FALLBACK_PLAYER_LABEL if event.player_id_value is None else self._player_name(PlayerId(event.player_id_value))
        prose = f"{actor_label}が{loc_name}に着きました。"
        structured = {"type": "player_entered_location", "actor": actor_label, "location_name": loc_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_location_exited(
        self, event: LocationExitedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ロケーションを出ました。"
        structured = {"type": "location_exited"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_player_location_changed(
        self, event: PlayerLocationChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        spot_name = self._spot_name(event.new_spot_id)
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = f"現在地: {spot_name}"
            structured = {"type": "current_location", "spot_name": spot_name, "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_name = self._player_name(event.aggregate_id)
        prose = f"{actor_name}がこのスポットにやってきました。"
        structured = {"type": "player_entered_spot", "actor": actor_name, "spot_name": spot_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_player_downed(
        self, event: PlayerDownedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "戦闘不能になりました。"
            structured = {"type": "player_downed", "role": "self"}
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True
            )
        actor_name = self._player_name(event.aggregate_id)
        prose = f"{actor_name}が戦闘不能になりました。"
        structured = {"type": "player_downed", "actor": actor_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_player_revived(
        self, event: PlayerRevivedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "復帰しました。"
            structured = {"type": "player_revived", "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_name = self._player_name(event.aggregate_id)
        prose = f"{actor_name}が復帰しました。"
        structured = {"type": "player_revived", "actor": actor_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_player_level_up(
        self, event: PlayerLevelUpEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"レベルが上がりました（{event.old_level} → {event.new_level}）。"
        structured = {"type": "level_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_player_gold_earned(
        self, event: PlayerGoldEarnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.earned_amount}ゴールドを獲得しました。"
        structured = {"type": "gold_earned", "amount": event.earned_amount}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_player_gold_paid(
        self, event: PlayerGoldPaidEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.paid_amount}ゴールドを支払いました。"
        structured = {"type": "gold_paid", "amount": event.paid_amount}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_taken_from_chest(
        self, event: ItemTakenFromChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"チェストから{item_name}を取得しました。"
        structured = {"type": "item_taken_from_chest", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_stored_in_chest(
        self, event: ItemStoredInChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"チェストに{item_name}を収納しました。"
        structured = {"type": "item_stored_in_chest", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

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
                spec_id_value = int(spec_id_raw) if not isinstance(spec_id_raw, int) else spec_id_raw
            except (TypeError, ValueError):
                parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
                continue
            name = self._item_spec_name(spec_id_value)
            parts.append(f"{name}を{qty}個")
        if not parts:
            prose = "採集しました。"
            structured = {"type": "resource_harvested", "items": []}
        else:
            item_desc = "、".join(parts)
            prose = f"採集し、{item_desc}入手しました。"
            structured = {"type": "resource_harvested", "items": event.obtained_items}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        old_s = event.old_weather_state.weather_type.value
        new_s = event.new_weather_state.weather_type.value
        prose = f"天気が{old_s}から{new_s}に変わりました。"
        structured = {"type": "weather_changed", "old": old_s, "new": new_s}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _interaction_type_to_prose(self, interaction_type: InteractionTypeEnum, data: Dict[str, Any]) -> str:
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

    def _format_world_object_interacted(
        self, event: WorldObjectInteractedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = self._interaction_type_to_prose(event.interaction_type, event.data or {})
        structured = {
            "type": "object_interacted",
            "interaction_type": event.interaction_type.value,
        }
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_added_to_inventory(
        self, event: ItemAddedToInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        agg = None
        if self._item_repository:
            agg = self._item_repository.find_by_id(event.item_instance_id)
        qty = agg.quantity if agg is not None else 1
        if qty != 1:
            prose = f"{item_name}を{qty}個入手しました。"
        else:
            prose = f"{item_name}を入手しました。"
        structured = {"type": "item_added_to_inventory", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True
        )

    def _format_item_dropped(
        self, event: ItemDroppedFromInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"{item_name}を捨てました。"
        structured = {"type": "item_dropped", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_equipped(
        self, event: ItemEquippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"{item_name}を装備しました。"
        structured = {"type": "item_equipped", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_unequipped(
        self, event: ItemUnequippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"{item_name}を外しました。"
        structured = {"type": "item_unequipped", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_inventory_slot_overflow(
        self, event: InventorySlotOverflowEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.overflowed_item_instance_id)
        prose = f"インベントリが満杯で{item_name}が溢れました。"
        structured = {"type": "inventory_overflow", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
