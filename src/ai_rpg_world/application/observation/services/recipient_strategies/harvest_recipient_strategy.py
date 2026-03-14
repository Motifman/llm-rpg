"""採集（Harvest）イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)


class HarvestRecipientStrategy(IRecipientResolutionStrategy):
    """Harvest イベントの配信先（actor のプレイヤー本人）を返す。"""

    _STRATEGY_KEY = "harvest"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
    ) -> None:
        self._registry = observed_event_registry
        self._world_object_to_player_resolver = world_object_to_player_resolver

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(
            event, (HarvestStartedEvent, HarvestCancelledEvent, HarvestCompletedEvent)
        ):
            return []
        pid = self._world_object_to_player_resolver.resolve_player_id(event.actor_id)
        return [pid] if pid is not None else []

