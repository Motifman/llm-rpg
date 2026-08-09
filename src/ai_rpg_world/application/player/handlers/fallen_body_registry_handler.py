"""down / revive の domain event から身体位置の真実の源を更新する。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


class RecordFallenBodyHandler:
    """倒れた瞬間の graph 位置を一度だけ身体記録へ固定する。"""

    def __init__(
        self,
        *,
        registry: FallenBodyRegistry,
        spot_graph_repository: ISpotGraphRepository,
        current_tick_provider: Callable[[], int],
    ) -> None:
        self._registry = registry
        self._spot_graph_repository = spot_graph_repository
        self._current_tick_provider = current_tick_provider

    def handle(self, event: PlayerDownedEvent) -> None:
        player_id = PlayerId(int(event.aggregate_id))
        graph = self._spot_graph_repository.find_graph()
        spot_id = graph.get_entity_spot(EntityId.create(int(player_id)))
        self._registry.record(
            player_id,
            spot_id,
            WorldTick(self._current_tick_provider()),
        )


class RemoveFallenBodyOnReviveHandler:
    """蘇生した身体を記録から除き、古い死体を世界に残さない。"""

    def __init__(self, registry: FallenBodyRegistry) -> None:
        self._registry = registry

    def handle(self, event: PlayerRevivedEvent) -> None:
        self._registry.remove(PlayerId(int(event.aggregate_id)))


__all__ = ["RecordFallenBodyHandler", "RemoveFallenBodyOnReviveHandler"]
