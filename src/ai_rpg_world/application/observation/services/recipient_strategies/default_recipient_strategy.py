"""観測対象イベント全体を扱うデフォルト配信先解決戦略（既存ロジックを集約）"""

from typing import Any, List, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
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


class DefaultRecipientStrategy(IRecipientResolutionStrategy):
    """
    既存の観測対象イベントすべてに対する配信先解決。
    Gateway / マップ / プレイヤー状態 / インベントリ系を一括で扱う。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._world_object_to_player_resolver = world_object_to_player_resolver

    def supports(self, event: Any) -> bool:
        """観測対象として定義されているイベント型なら True。"""
        return (
            isinstance(event, LocationEnteredEvent)
            or isinstance(event, LocationExitedEvent)
            or isinstance(event, PlayerLocationChangedEvent)
            or isinstance(event, PlayerDownedEvent)
            or isinstance(event, PlayerRevivedEvent)
            or isinstance(event, PlayerLevelUpEvent)
            or isinstance(event, PlayerGoldEarnedEvent)
            or isinstance(event, PlayerGoldPaidEvent)
            or isinstance(event, ItemTakenFromChestEvent)
            or isinstance(event, ItemStoredInChestEvent)
            or isinstance(event, ResourceHarvestedEvent)
            or isinstance(event, SpotWeatherChangedEvent)
            or isinstance(event, WorldObjectInteractedEvent)
            or isinstance(event, ItemAddedToInventoryEvent)
            or isinstance(event, ItemDroppedFromInventoryEvent)
            or isinstance(event, ItemEquippedEvent)
            or isinstance(event, ItemUnequippedEvent)
            or isinstance(event, InventorySlotOverflowEvent)
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        """配信先プレイヤーIDのリストを返す（重複あり。Resolver が重複除去する）。"""
        result: List[PlayerId] = []
        seen: Set[int] = set()

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        if isinstance(event, LocationEnteredEvent):
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
            pid = self._world_object_to_player_resolver.resolve_player_id(
                event.actor_id
            )
            if pid is not None:
                add(pid)
        elif isinstance(event, SpotWeatherChangedEvent):
            self._resolve_spot_weather_changed(event, add)
        elif isinstance(event, WorldObjectInteractedEvent):
            pid = self._world_object_to_player_resolver.resolve_player_id(
                event.actor_id
            )
            if pid is not None:
                add(pid)
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

        return result

    def _players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        all_statuses = self._player_status_repository.find_all()
        return [
            s.player_id
            for s in all_statuses
            if s.current_spot_id is not None
            and s.current_spot_id.value == spot_id.value
        ]

    def _resolve_location_entered(
        self, event: LocationEnteredEvent, add
    ) -> None:
        if event.player_id_value is not None:
            add(PlayerId(event.player_id_value))
        for pid in self._players_at_spot(event.spot_id):
            add(pid)

    def _resolve_location_exited(self, event: LocationExitedEvent, add) -> None:
        pid = self._world_object_to_player_resolver.resolve_player_id(
            event.object_id
        )
        if pid is not None:
            add(pid)

    def _resolve_player_location_changed(
        self, event: PlayerLocationChangedEvent, add
    ) -> None:
        add(event.aggregate_id)
        for pid in self._players_at_spot(event.new_spot_id):
            add(pid)

    def _resolve_player_downed(self, event: PlayerDownedEvent, add) -> None:
        add(event.aggregate_id)

    def _resolve_player_revived(self, event: PlayerRevivedEvent, add) -> None:
        add(event.aggregate_id)

    def _resolve_item_stored_in_chest(
        self, event: ItemStoredInChestEvent, add
    ) -> None:
        add(PlayerId(event.player_id_value))
        for pid in self._players_at_spot(event.spot_id):
            add(pid)

    def _resolve_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, add
    ) -> None:
        for pid in self._players_at_spot(event.spot_id):
            add(pid)
