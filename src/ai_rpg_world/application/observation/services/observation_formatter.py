"""観測テキスト（プローズ＋構造化）を生成するフォーマッタ実装"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import IObservationFormatter
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
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


class ObservationFormatter(IObservationFormatter):
    """
    イベント＋配信先を観測テキスト（プローズ文と構造化 dict）に変換する。
    仕様の「観測内容（例）」に基づく。名前解決は任意のリポジトリで行う。
    """

    def __init__(
        self,
        spot_repository: Optional["SpotRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
    ) -> None:
        self._spot_repository = spot_repository
        self._player_profile_repository = player_profile_repository

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
        attention_level: Optional[str] = None,
    ) -> Optional[ObservationOutput]:
        """指定プレイヤー向けの観測出力を生成。attention_level は将来用で未使用。"""
        if isinstance(event, GatewayTriggeredEvent):
            return self._format_gateway_triggered(event, recipient_player_id)
        if isinstance(event, LocationEnteredEvent):
            return self._format_location_entered(event, recipient_player_id)
        if isinstance(event, LocationExitedEvent):
            return self._format_location_exited(event, recipient_player_id)
        if isinstance(event, PlayerLocationChangedEvent):
            return self._format_player_location_changed(event, recipient_player_id)
        if isinstance(event, PlayerDownedEvent):
            return self._format_player_downed(event, recipient_player_id)
        if isinstance(event, PlayerRevivedEvent):
            return self._format_player_revived(event, recipient_player_id)
        if isinstance(event, PlayerLevelUpEvent):
            return self._format_player_level_up(event, recipient_player_id)
        if isinstance(event, PlayerGoldEarnedEvent):
            return self._format_player_gold_earned(event, recipient_player_id)
        if isinstance(event, PlayerGoldPaidEvent):
            return self._format_player_gold_paid(event, recipient_player_id)
        if isinstance(event, ItemTakenFromChestEvent):
            return self._format_item_taken_from_chest(event, recipient_player_id)
        if isinstance(event, ItemStoredInChestEvent):
            return self._format_item_stored_in_chest(event, recipient_player_id)
        if isinstance(event, SpotWeatherChangedEvent):
            return self._format_spot_weather_changed(event, recipient_player_id)
        if isinstance(event, WorldObjectInteractedEvent):
            return self._format_world_object_interacted(event, recipient_player_id)
        if isinstance(event, ItemAddedToInventoryEvent):
            return self._format_item_added_to_inventory(event, recipient_player_id)
        if isinstance(event, ItemDroppedFromInventoryEvent):
            return self._format_item_dropped(event, recipient_player_id)
        if isinstance(event, ItemEquippedEvent):
            return self._format_item_equipped(event, recipient_player_id)
        if isinstance(event, ItemUnequippedEvent):
            return self._format_item_unequipped(event, recipient_player_id)
        if isinstance(event, InventorySlotOverflowEvent):
            return self._format_inventory_slot_overflow(event, recipient_player_id)
        return None

    def _spot_name(self, spot_id: SpotId) -> str:
        if self._spot_repository:
            spot = self._spot_repository.find_by_id(spot_id)
            if spot:
                return getattr(spot, "name", str(spot_id.value))
        return f"スポット{spot_id.value}"

    def _player_name(self, player_id: PlayerId) -> str:
        if self._player_profile_repository:
            profile = self._player_profile_repository.find_by_id(player_id)
            if profile and hasattr(profile, "name"):
                return getattr(profile.name, "value", str(player_id.value))
        return f"プレイヤー{player_id.value}"

    def _format_gateway_triggered(
        self, event: GatewayTriggeredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        target_name = self._spot_name(event.target_spot_id)
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{target_name}に到着しました。"
            structured = {"type": "gateway_arrival", "spot_name": target_name, "role": "self"}
        else:
            # 他プレイヤー向け: 「〇〇がこのスポットにやってきました」
            actor_label = f"誰か" if event.player_id_value is None else self._player_name(PlayerId(event.player_id_value))
            prose = f"{actor_label}がこのスポットにやってきました。"
            structured = {"type": "player_entered_spot", "actor": actor_label, "spot_name": target_name}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_location_entered(
        self, event: LocationEnteredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        loc_name = getattr(event, "name", f"ロケーション{event.location_id}")
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{loc_name}に着きました。"
            structured = {"type": "location_entered", "location_name": loc_name, "role": "self"}
        else:
            actor_label = "誰か" if event.player_id_value is None else self._player_name(PlayerId(event.player_id_value))
            prose = f"{actor_label}が{loc_name}に着きました。"
            structured = {"type": "player_entered_location", "actor": actor_label, "location_name": loc_name}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_location_exited(
        self, event: LocationExitedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ロケーションを出ました。"
        structured = {"type": "location_exited"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_player_location_changed(
        self, event: PlayerLocationChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        spot_name = self._spot_name(event.new_spot_id)
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = f"現在地: {spot_name}"
            structured = {"type": "current_location", "spot_name": spot_name, "role": "self"}
        else:
            actor_name = self._player_name(event.aggregate_id)
            prose = f"{actor_name}がこのスポットにやってきました。"
            structured = {"type": "player_entered_spot", "actor": actor_name, "spot_name": spot_name}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_player_downed(
        self, event: PlayerDownedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "戦闘不能になりました。"
            structured = {"type": "player_downed", "role": "self"}
        else:
            actor_name = self._player_name(event.aggregate_id)
            prose = f"{actor_name}が戦闘不能になりました。"
            structured = {"type": "player_downed", "actor": actor_name}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_player_revived(
        self, event: PlayerRevivedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "復帰しました。"
            structured = {"type": "player_revived", "role": "self"}
        else:
            actor_name = self._player_name(event.aggregate_id)
            prose = f"{actor_name}が復帰しました。"
            structured = {"type": "player_revived", "actor": actor_name}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_player_level_up(
        self, event: PlayerLevelUpEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"レベルが上がりました（{event.old_level} → {event.new_level}）。"
        structured = {"type": "level_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_player_gold_earned(
        self, event: PlayerGoldEarnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.earned_amount}ゴールドを獲得しました。"
        structured = {"type": "gold_earned", "amount": event.earned_amount}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_player_gold_paid(
        self, event: PlayerGoldPaidEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.paid_amount}ゴールドを支払いました。"
        structured = {"type": "gold_paid", "amount": event.paid_amount}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_item_taken_from_chest(
        self, event: ItemTakenFromChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "チェストからアイテムを取得しました。"
        structured = {"type": "item_taken_from_chest"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_item_stored_in_chest(
        self, event: ItemStoredInChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "チェストにアイテムを収納しました。"
        structured = {"type": "item_stored_in_chest"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        old_s = getattr(
            getattr(event.old_weather_state, "weather_type", event.old_weather_state),
            "name",
            str(event.old_weather_state),
        )
        new_s = getattr(
            getattr(event.new_weather_state, "weather_type", event.new_weather_state),
            "name",
            str(event.new_weather_state),
        )
        prose = f"天気が{old_s}から{new_s}に変わりました。"
        structured = {"type": "weather_changed", "old": old_s, "new": new_s}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_world_object_interacted(
        self, event: WorldObjectInteractedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "オブジェクトとインタラクションしました。"
        structured = {"type": "object_interacted"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_item_added_to_inventory(
        self, event: ItemAddedToInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "アイテムを入手しました。"
        structured = {"type": "item_added_to_inventory"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_item_dropped(
        self, event: ItemDroppedFromInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "アイテムを捨てました。"
        structured = {"type": "item_dropped"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_item_equipped(
        self, event: ItemEquippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "アイテムを装備しました。"
        structured = {"type": "item_equipped"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_item_unequipped(
        self, event: ItemUnequippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "アイテムを外しました。"
        structured = {"type": "item_unequipped"}
        return ObservationOutput(prose=prose, structured=structured)

    def _format_inventory_slot_overflow(
        self, event: InventorySlotOverflowEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "インベントリが満杯でアイテムが溢れました。"
        structured = {"type": "inventory_overflow"}
        return ObservationOutput(prose=prose, structured=structured)
