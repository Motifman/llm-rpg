"""観測配信先をイベントから解決する実装"""

from typing import Any, List, Optional, Set

from ai_rpg_world.application.observation.contracts.interfaces import IObservationRecipientResolver
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
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


class ObservationRecipientResolver(IObservationRecipientResolver):
    """
    ドメインイベントから観測の配信先プレイヤーID一覧を解決する。
    仕様（domain_events_observation_spec.md）の「配信先」に基づく。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        physical_map_repository: PhysicalMapRepository,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._physical_map_repository = physical_map_repository

    def resolve(self, event: Any) -> List[PlayerId]:
        """イベント種別に応じて配信先を返す。観測対象外または未知のイベントは空リスト。"""
        seen: Set[int] = set()
        result: List[PlayerId] = []

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        if isinstance(event, GatewayTriggeredEvent):
            self._resolve_gateway_triggered(event, add)
        elif isinstance(event, LocationEnteredEvent):
            self._resolve_location_entered(event, add)
        elif isinstance(event, LocationExitedEvent):
            self._resolve_location_exited(event, add)
        elif isinstance(event, PlayerLocationChangedEvent):
            self._resolve_player_location_changed(event, add)
        elif isinstance(event, PlayerDownedEvent):
            self._resolve_player_downed(event, add)
        elif isinstance(event, PlayerRevivedEvent):
            self._resolve_player_revived(event, add)
        elif isinstance(event, PlayerLevelUpEvent):
            add(event.aggregate_id)
        elif isinstance(event, PlayerGoldEarnedEvent):
            add(event.aggregate_id)
        elif isinstance(event, PlayerGoldPaidEvent):
            add(event.aggregate_id)
        elif isinstance(event, ItemTakenFromChestEvent):
            add(PlayerId(event.player_id_value))
        elif isinstance(event, ItemStoredInChestEvent):
            self._resolve_item_stored_in_chest(event, add)
        elif isinstance(event, ResourceHarvestedEvent):
            pid = self._resolve_player_id_from_world_object_id(event.actor_id)
            if pid is not None:
                add(pid)
        elif isinstance(event, SpotWeatherChangedEvent):
            self._resolve_spot_weather_changed(event, add)
        elif isinstance(event, WorldObjectInteractedEvent):
            self._resolve_world_object_interacted(event, add)
        elif isinstance(event, ItemAddedToInventoryEvent):
            add(event.aggregate_id)
        elif isinstance(event, ItemDroppedFromInventoryEvent):
            add(event.aggregate_id)
        elif isinstance(event, ItemEquippedEvent):
            add(event.aggregate_id)
        elif isinstance(event, ItemUnequippedEvent):
            add(event.aggregate_id)
        elif isinstance(event, InventorySlotOverflowEvent):
            add(event.aggregate_id)
        # その他イベントは観測対象外として空リストのまま

        return result

    def _players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        all_statuses = self._player_status_repository.find_all()
        return [
            s.player_id
            for s in all_statuses
            if s.current_spot_id is not None and s.current_spot_id.value == spot_id.value
        ]

    def _resolve_gateway_triggered(self, event: GatewayTriggeredEvent, add) -> None:
        for pid in self._players_at_spot(event.target_spot_id):
            add(pid)
        if event.player_id_value is not None:
            add(PlayerId(event.player_id_value))

    def _resolve_location_entered(self, event: LocationEnteredEvent, add) -> None:
        if event.player_id_value is not None:
            add(PlayerId(event.player_id_value))
        for pid in self._players_at_spot(event.spot_id):
            add(pid)

    def _resolve_location_exited(self, event: LocationExitedEvent, add) -> None:
        pid = self._resolve_player_id_from_world_object_id(event.object_id)
        if pid is not None:
            add(pid)

    def _resolve_player_location_changed(self, event: PlayerLocationChangedEvent, add) -> None:
        add(event.aggregate_id)
        for pid in self._players_at_spot(event.new_spot_id):
            add(pid)

    def _resolve_player_downed(self, event: PlayerDownedEvent, add) -> None:
        add(event.aggregate_id)
        # 同一スポット・視界内は簡略化のためここでは本人のみ

    def _resolve_player_revived(self, event: PlayerRevivedEvent, add) -> None:
        add(event.aggregate_id)

    def _resolve_item_stored_in_chest(self, event: ItemStoredInChestEvent, add) -> None:
        add(PlayerId(event.player_id_value))
        for pid in self._players_at_spot(event.spot_id):
            add(pid)

    def _resolve_spot_weather_changed(self, event: SpotWeatherChangedEvent, add) -> None:
        for pid in self._players_at_spot(event.spot_id):
            add(pid)

    def _resolve_world_object_interacted(self, event: WorldObjectInteractedEvent, add) -> None:
        pid = self._resolve_player_id_from_world_object_id(event.actor_id)
        if pid is not None:
            add(pid)

    def _resolve_player_id_from_world_object_id(
        self, object_id: WorldObjectId
    ) -> Optional[PlayerId]:
        """WorldObjectId に紐づくプレイヤーIDを解決する。プレイヤーでなければ None。"""
        spot_id = self._physical_map_repository.find_spot_id_by_object_id(object_id)
        if spot_id is None:
            return None
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map is None:
            return None
        try:
            obj = physical_map.get_object(object_id)
        except ObjectNotFoundException:
            return None
        return obj.player_id
