"""アイテム使用イベントの観測配信先解決（スポットグラフモード）。

ConsumableUsedEvent を受け取り、使用者と同じスポットにいる
他プレイヤーに配信する。使用者本人は除外する。
"""

from typing import Any, List, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


class ItemUseRecipientStrategy(IRecipientResolutionStrategy):
    """アイテム使用を同スポットの他プレイヤーに配信する。"""

    _STRATEGY_KEY = "item_use"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._registry = observed_event_registry
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(event, ConsumableUsedEvent):
            return []

        player_id = event.aggregate_id  # PlayerId
        entity_id = EntityId.create(player_id.value)

        graph = self._spot_graph_repository.find_graph()
        try:
            spot_id = graph.get_entity_spot(entity_id)
        except Exception:
            return []

        entity_spot = graph.entity_spot_mapping()
        known_player_ids: Set[int] = {
            s.player_id.value
            for s in self._player_status_repository.find_all()
        }

        result: List[PlayerId] = []
        for eid, sid in entity_spot.items():
            if sid == spot_id and eid.value in known_player_ids and eid.value != player_id.value:
                result.append(PlayerId(eid.value))
        return result
