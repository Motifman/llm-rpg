"""採集（Harvest）イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)


class HarvestRecipientStrategy(IRecipientResolutionStrategy):
    """Harvest イベントの配信先（actor のプレイヤー本人）を返す。"""

    def __init__(self, world_object_to_player_resolver: IWorldObjectToPlayerResolver) -> None:
        self._world_object_to_player_resolver = world_object_to_player_resolver

    def supports(self, event: Any) -> bool:
        return isinstance(
            event, (HarvestStartedEvent, HarvestCancelledEvent, HarvestCompletedEvent)
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(
            event, (HarvestStartedEvent, HarvestCancelledEvent, HarvestCompletedEvent)
        ):
            return []
        pid = self._world_object_to_player_resolver.resolve_player_id(event.actor_id)
        return [pid] if pid is not None else []

